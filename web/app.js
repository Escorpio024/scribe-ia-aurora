(() => {
  const $ = s => document.querySelector(s);
  const log = (...a) => {
    const el = $('#logs');
    el.textContent += a.map(x => typeof x==='string'?x:JSON.stringify(x)).join(' ') + '\n';
    el.scrollTop=el.scrollHeight;
  };
  const setText = (id, txt, cls) => {
    const el=$(id); el.textContent=txt||''; if(cls) el.className=`tiny ${cls}`;
  };

  let mediaStream=null, audioCtx=null, workletNode=null;
  let recorded=[], wavBlob=null, sampleRate=48000;
  const TARGET_SR = 16000;

  // -------- Audio --------
  const workletCode = `
  class MonoCaptureProcessor extends AudioWorkletProcessor {
    process(inputs){ const i=inputs[0]; if(i && i[0]){ const ch=i[0]; const cp=new Float32Array(ch.length); cp.set(ch); this.port.postMessage(cp,[cp.buffer]); } return true; }
  }
  registerProcessor('mono-capture', MonoCaptureProcessor);`;
  const workletURL = URL.createObjectURL(new Blob([workletCode], {type:'application/javascript'}));

  function downsampleBuffer(buffer, fromRate, toRate){
    if (toRate===fromRate) return buffer;
    const ratio=fromRate/toRate, newLen=Math.round(buffer.length/ratio);
    const out=new Float32Array(newLen); let pos=0;
    for(let i=0;i<newLen;i++){ out[i]=buffer[Math.floor(pos)]; pos+=ratio; }
    return out;
  }
  function floatTo16BitPCM(floatBuf){ const out=new Int16Array(floatBuf.length);
    for(let i=0;i<floatBuf.length;i++){ let s=Math.max(-1,Math.min(1,floatBuf[i])); out[i]= s<0 ? s*0x8000 : s*0x7FFF; } return out; }
  function encodeWAV(int16, sr){
    const ch=1,bps=2,ba=ch*bps; const buf=new ArrayBuffer(44+int16.length*bps); const v=new DataView(buf);
    write('RIFF',0); v.setUint32(4,36+int16.length*bps,true);
    write('WAVE',8); write('fmt ',12); v.setUint32(16,16,true);
    v.setUint16(20,1,true); v.setUint16(22,ch,true);
    v.setUint32(24,sr,true); v.setUint32(28,sr*ba,true);
    v.setUint16(32,ba,true); v.setUint16(34,16,true);
    write('data',36); v.setUint32(40,int16.length*bps,true);
    let o=44; for(let i=0;i<int16.length;i++,o+=2) v.setInt16(o,int16[i],true);
    return new Blob([v], {type:'audio/wav'});
    function write(s,off){ for(let i=0;i<s.length;i++) v.setUint8(off+i, s.charCodeAt(i)); }
  }

  async function startRecording(){
    try{
      if(!navigator.mediaDevices?.getUserMedia) throw new Error('getUserMedia no disponible');
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation:true, noiseSuppression:true, autoGainControl:true, channelCount:1 }});
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      sampleRate = audioCtx.sampleRate;
      await audioCtx.audioWorklet.addModule(workletURL);
      const source = audioCtx.createMediaStreamSource(mediaStream);
      workletNode = new AudioWorkletNode(audioCtx,'mono-capture');
      recorded=[]; workletNode.port.onmessage = e => recorded.push(new Float32Array(e.data));
      source.connect(workletNode);
      $('#btnStart').disabled=true; $('#btnPause').disabled=false; $('#btnResume').disabled=true; $('#btnStop').disabled=false; $('#btnUpload').disabled=true;
      setText('#recStatus', `Grabando... SR=${sampleRate}`, 'ok'); log('🔊 AudioWorklet cargado'); log('🎙️ Grabación iniciada.');
    }catch(e){ log('❌ Error getUserMedia/Worklet:', e); setText('#recStatus','Permiso de micrófono o contexto no seguro. Usa http://localhost o HTTPS.','err'); }
  }
  function pauseRecording(){ if(audioCtx?.state==='running'){ audioCtx.suspend(); $('#btnPause').disabled=true; $('#btnResume').disabled=false; setText('#recStatus','Pausado','warn'); log('⏸️ Pausa.'); } }
  async function resumeRecording(){ if(audioCtx?.state==='suspended'){ await audioCtx.resume(); $('#btnPause').disabled=false; $('#btnResume').disabled=true; setText('#recStatus','Grabando…','ok'); log('▶️ Resume.'); } }
  async function stopRecording(){
    if(!audioCtx) return;
    try{ mediaStream?.getTracks()?.forEach(t=>t.stop()); }catch{}; try{ await audioCtx.close(); }catch{}
    const total = recorded.reduce((n,ch)=>n+ch.length,0);
    const pcm = new Float32Array(total); let off=0; for(const ch of recorded){ pcm.set(ch, off); off+=ch.length; }
    const ds = downsampleBuffer(pcm, sampleRate, TARGET_SR);
    const i16 = floatTo16BitPCM(ds); wavBlob = encodeWAV(i16, TARGET_SR);
    $('#audioPreview').src = URL.createObjectURL(wavBlob);
    $('#btnStart').disabled=false; $('#btnPause').disabled=true; $('#btnResume').disabled=true; $('#btnStop').disabled=true; $('#btnUpload').disabled=!wavBlob;
    setText('#recStatus',`Grabado (${Math.round(ds.length/TARGET_SR)}s)`,'ok'); log(`✅ WAV listo (${Math.round(wavBlob.size/1024)} KiB, 16k mono)`);
  }

  function makeEncounterId(){ const d=new Date(), pad=n=>n.toString().padStart(2,'0'); return `enc_web_${d.getFullYear()}${pad(d.getMonth()+1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`; }

  // -------- Helpers de paciente --------
  function readPatientForm(){
  const epsSel = document.getElementById('eps');
  const epsOther = document.getElementById('epsOther');
  const epsValue = (epsSel?.value === 'OTRA') ? (epsOther?.value?.trim() || '') : (epsSel?.value || '');

  return {
    nombre_paciente: document.getElementById('patientName')?.value.trim() || undefined,
    identificacion: {
      tipo: document.getElementById('idType')?.value.trim() || undefined,
      numero: document.getElementById('idNumber')?.value.trim() || undefined
    },
    fecha_nacimiento: document.getElementById('dob')?.value.trim() || undefined,
    edad: document.getElementById('age')?.value.trim() || undefined,
    sexo: document.getElementById('sex')?.value.trim() || undefined,
    direccion: document.getElementById('address')?.value.trim() || undefined,
    telefono: document.getElementById('phone')?.value.trim() || undefined,
    eps: epsValue || undefined
  };
}
  function mergePatientIntoJson(j){
    const p = readPatientForm();
    if (!j.paciente) j.paciente = {};
    if (p.nombre_paciente) j.paciente.nombre = p.nombre_paciente;
    if (p.identificacion?.tipo || p.identificacion?.numero) {
      j.paciente.identificacion = {
        ...(j.paciente.identificacion||{}),
        ...p.identificacion
      };
    }
    if (p.fecha_nacimiento) j.paciente.fecha_nacimiento = p.fecha_nacimiento;
    if (p.edad) j.edad = p.edad;
    if (p.sexo) j.sexo = p.sexo;
    if (p.direccion) j.paciente.direccion = p.direccion;
    if (p.telefono) j.paciente.telefono = p.telefono;
    if (p.eps) j.paciente.eps = p.eps;
    return j;
  }

  // -------- CDS helper --------
  async function fetchCdsSuggestions(apiBase, jsonClinico, schemaUsed) {
    function formatEA(ea) {
      if (!ea) return '';
      if (typeof ea === 'string') return ea;
      if (typeof ea === 'object') {
        const parts = [];
        if (ea.inicio) parts.push(ea.inicio);
        if (ea.evolucion) parts.push(ea.evolucion);
        if (ea.sintomas) parts.push(ea.sintomas);
        if (ea.descripcion) parts.push(ea.descripcion);
        if (ea.texto) parts.push(ea.texto);
        return parts.length > 0 ? parts.join(' ') : JSON.stringify(ea);
      }
      return String(ea);
    }
    const ctx = {
      chief_complaint: jsonClinico.motivo_consulta || (schemaUsed || ''),
      diagnosis: Array.isArray(jsonClinico.impresion_dx) && jsonClinico.impresion_dx.length ? jsonClinico.impresion_dx[0] : '',
      symptoms: formatEA(jsonClinico.enfermedad_actual),
      age: jsonClinico.edad || jsonClinico.age || null,
      alergias: Array.isArray(jsonClinico.alergias) ? jsonClinico.alergias : [],
    };
    const payload = { context: ctx, use_pubmed: true, pubmed_max: 5 };
    try {
      const resp = await fetch(`${apiBase}/cds/suggest`, {
        method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
      });
      if (!resp.ok) { log('❌ /cds/suggest', resp.status); return []; }
      const data = await resp.json();
      return Array.isArray(data.suggestions) ? data.suggestions : [];
    } catch(e) { log('❌ CDS fetch', e); return []; }
  }

  // -------- Ingest --------
  async function doIngest(){
    const apiBase=$('#apiBase').value.trim();
    let enc=$('#encounterId').value.trim();
    if(!enc){ enc=makeEncounterId(); $('#encounterId').value=enc; }
    if(!wavBlob){ setText('#ingestMsg','No hay audio grabado','err'); log('❌ No hay audio para subir'); return; }

    const form=new FormData();
    form.append('wav', wavBlob, 'consulta.wav');
    setText('#ingestMsg','Subiendo...','warn');
    log(`📤 Subiendo audio a: ${apiBase}/ingest/upload?encounter_id=${enc}`);

    try{
      const resp=await fetch(`${apiBase}/ingest/upload?encounter_id=${encodeURIComponent(enc)}`,{ method:'POST', body:form });
      log(`📥 Respuesta HTTP: ${resp.status} ${resp.statusText}`);
      const text=await resp.text();

      if(!resp.ok){ setText('#ingestMsg',`Error ${resp.status}`,'err'); log('❌ Error del servidor:', text); return; }

      let data;
      try { data = JSON.parse(text); }
      catch(parseErr) { setText('#ingestMsg','Respuesta inválida del servidor','err'); log('❌ JSON inválido:', text); return; }

      log('✅ Respuesta del servidor:', data);

      const incoming=Array.isArray(data.transcript)?data.transcript:[];
      if(incoming.length>0) {
        $('#transcriptBox').value = JSON.stringify(incoming, null, 2);
        log(`📝 Transcript recibido: ${incoming.length} segmentos`);
      } else {
        log('⚠️ No se recibió transcript o está vacío');
      }

      $('#btnGen').disabled=false;
      setText('#ingestMsg','OK','ok');
      log('⬆️ Upload completado. Botón "Generar Historia" habilitado');
    }catch(e){
      setText('#ingestMsg',`Error: ${e.message}`,'err');
      log('❌ Error de red o conexión:', e);
    }
  }

  // -------- Compactar EA --------
  function compactEA(ea) {
    if (!ea) return ea;
    if (typeof ea === 'object') return ea;
    const str = String(ea).replace(/\s+/g,' ').trim();
    const MAX = 350;
    if (str.length <= MAX) return str;
    const parts = str.split(/(?<=\.)\s+/).filter(Boolean);
    let out = [];
    for (const p of parts) {
      out.push(p);
      if (out.join(' ').length > MAX) break;
    }
    let summary = out.join(' ').trim();
    if (summary.length > MAX) summary = summary.slice(0, MAX - 1).trim() + '…';
    return summary;
  }

  // -------- Generate --------
  async function doGenerate(){
    const apiBase=$('#apiBase').value.trim();
    const encounter_id=$('#encounterId').value.trim() || makeEncounterId();
    $('#encounterId').value=encounter_id;

    const body={
      encounter_id,
      patient_id: $('#patientId').value.trim()||'pat1',
      practitioner_id: $('#practitionerId').value.trim()||'doc1',
      schema_id: $('#schemaId').value,
      transcript: []
    };

    const transcriptText = $('#transcriptBox').value.trim();
    log(`📋 Transcript actual: ${transcriptText || '(vacío)'}`);

    try{
      if(transcriptText) {
        const t=JSON.parse(transcriptText);
        if(!Array.isArray(t)) throw new Error('Transcript debe ser array');
        body.transcript=t;
        log(`✅ Transcript válido: ${t.length} elementos`);
      } else {
        log('⚠️ Transcript vacío, generando con array vacío');
        body.transcript = [];
      }
    }
    catch(e){
      setText('#genMsg','Transcript inválido (JSON)','err');
      log('❌ Error parseando transcript:', e);
      return;
    }

    setText('#genMsg','Generando...','warn');
    log(`📤 Enviando a ${apiBase}/nlp/generate:`, body);

    try{
      const resp=await fetch(`${apiBase}/nlp/generate`,{ method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
      log(`📥 Respuesta HTTP: ${resp.status} ${resp.statusText}`);
      const text=await resp.text();

      if(!resp.ok){ setText('#genMsg',`Error ${resp.status}`,'err'); log('❌ Error del servidor:', text); return; }

      let data;
      try {
        data=JSON.parse(text);

        // Enriquecer desde transcript (fallback UI)
        const enrich = extractAntecedentesRosFromTranscript(body.transcript);
        data.json_clinico = data.json_clinico || {};
        data.json_clinico.antecedentes = {
          ...(data.json_clinico.antecedentes || {}),
          ...(enrich.antecedentes || {})
        };
        data.json_clinico.revision_sistemas = {
          ...(data.json_clinico.revision_sistemas || {}),
          ...(enrich.revision_sistemas || {})
        };
        data.json_clinico.examen_fisico = {
          ...(data.json_clinico.examen_fisico || {}),
          ...(enrich.examen_fisico || {})
        };

        // Compactar enfermedad_actual si es larga
        if (data.json_clinico.enfermedad_actual) {
          data.json_clinico.enfermedad_actual = compactEA(data.json_clinico.enfermedad_actual);
        }

        // Mezclar datos de paciente del formulario
        data.json_clinico = mergePatientIntoJson(data.json_clinico);
      } catch(parseErr) {
        setText('#genMsg','Respuesta inválida del servidor','err');
        log('❌ JSON inválido:', text);
        return;
      }

      log('✅ Datos recibidos:', data);

      $('#jsonClinicoBox').value = JSON.stringify(data.json_clinico??{}, null, 2);
      $('#bundleBox').value = JSON.stringify(data.fhir_bundle??{}, null, 2);

      try{ renderHistoriaClinica(data.json_clinico??{}); }catch(e){ log('⚠️ renderHistoriaClinica error:', e); }
      setText('#genMsg','OK','ok');
      $('#btnPushApi').disabled=false;
      $('#btnPushHapi').disabled=false;
      log('🧠 Historia generada exitosamente');

      renderBlocks(data.json_clinico??{});

      const builtIn = Array.isArray(data.cds_suggestions) ? data.cds_suggestions : [];
      if (builtIn.length) renderSuggestions(builtIn);

      const extra = await fetchCdsSuggestions(apiBase, data.json_clinico||{}, data.schema_used||'');
      const seen = new Set((builtIn||[]).map(x => (x.message||x.proposed||'').trim().toLowerCase()));
      const merged = builtIn.slice();
      for (const it of extra) {
        const key = (it.message||it.proposed||'').trim().toLowerCase();
        if (key && !seen.has(key)) { merged.push(it); seen.add(key); }
      }
      renderSuggestions(merged);
    }catch(e){
      setText('#genMsg',`Error: ${e.message}`,'err');
      log('❌ Error de red o conexión:', e);
    }
  }

  // -------- Formateadores para bloques --------
  function fmtAntecedentesToText(A){
    if (!A || typeof A!=='object') return '';
    const out=[];
    if (A.personales?.length) out.push(`Personales: ${Array.isArray(A.personales)?A.personales.join('; '):A.personales}`);
    if (A.patologicos?.length) out.push(`Patológicos: ${Array.isArray(A.patologicos)?A.patologicos.join('; '):A.patologicos}`);
    if (A.farmacologicos?.length) out.push(`Farmacológicos: ${Array.isArray(A.farmacologicos)?A.farmacologicos.join('; '):A.farmacologicos}`);
    if (A.alergias?.length) out.push(`Alergias: ${Array.isArray(A.alergias)?A.alergias.join('; '):A.alergias}`);
    if (A.habitos?.length) out.push(`Hábitos: ${Array.isArray(A.habitos)?A.habitos.join('; '):A.habitos}`);
    return out.join('\n');
  }
  function parseAntecedentesFromText(txt){
    const A={};
    const lines=(txt||'').split('\n').map(s=>s.trim()).filter(Boolean);
    for(const ln of lines){
      const m=ln.match(/^(\w+á?é?í?ó?ú?s?):\s*(.+)$/i);
      if(!m) continue;
      const key=m[1].toLowerCase();
      const vals=m[2].split(/;|,/).map(s=>s.trim()).filter(Boolean);
      if (/personal/.test(key)) A.personales = vals;
      else if (/patolog/.test(key)) A.patologicos = vals;
      else if (/farmacolog/.test(key)) A.farmacologicos = vals;
      else if (/alerg/.test(key)) A.alergias = vals;
      else if (/háb|habit/.test(key)) A.habitos = vals;
    }
    return A;
  }
  function fmtROSToText(ros){
    if (!ros || typeof ros!=='object') return '';
    const out=[];
    for(const [k,v] of Object.entries(ros)){
      const val = Array.isArray(v)? v.join('; '): (typeof v==='string'?v:JSON.stringify(v));
      out.push(`${k}: ${val}`);
    }
    return out.join('\n');
  }
  function parseROSFromText(txt){
    const R={};
    const lines=(txt||'').split('\n').map(s=>s.trim()).filter(Boolean);
    for(const ln of lines){
      const m=ln.match(/^([^:]+):\s*(.+)$/);
      if(!m) continue;
      const sys=m[1].trim().toLowerCase();
      const vals=m[2].split(/;|,/).map(s=>s.trim()).filter(Boolean);
      R[sys]=vals;
    }
    return R;
  }

  function renderBlocks(j){
    const root = document.querySelector('#hcBlocks'); root.innerHTML = '';
    const blocks = [
      { key:'motivo_consulta', title:'Motivo de consulta', type:'text' },
      { key:'enfermedad_actual', title:'Enfermedad actual', type:'text' },
      { key:'examen_fisico', title:'Examen físico', type:'vitals' },
      { key:'impresion_dx', title:'Impresión diagnóstica', type:'list' },
      { key:'ordenes', title:'Órdenes', type:'orders' },
      { key:'recetas', title:'Recetas', type:'orders' },
      { key:'alertas', title:'Alertas', type:'list' },
      { key:'antecedentes', title:'Antecedentes', type:'antecedentes' },
      { key:'revision_sistemas', title:'Revisión por sistemas', type:'ros' },
    ];
    for (const b of blocks){
      const card = document.createElement('div'); card.className='hc-block bg-gray-50';
      const header = document.createElement('header');
      header.innerHTML = `<span class="text-lg font-semibold text-gray-800">${b.title}</span><span class="tag bg-gray-200 text-gray-600">${b.key}</span>`;
      card.appendChild(header);
      const content = document.createElement('div'); content.className='hc-content text-gray-700'; content.setAttribute('data-key', b.key);

      if (b.type==='text') {
        content.contentEditable = "true";
        const raw = j[b.key] ?? '';
        content.textContent = typeof raw==='object' ? JSON.stringify(raw, null, 2) : String(raw);

      } else if (b.type==='vitals') {
        content.contentEditable = "true";
        const ef = j.examen_fisico || {};
        content.textContent = [
          ef.TA ? `TA: ${ef.TA}` : '',
          ef.FC ? `FC: ${ef.FC}` : '',
          ef.FR ? `FR: ${ef.FR}` : '',
          ef.Temp ? `Temp: ${ef.Temp}` : '',
          ef.SatO2 ? `SatO2: ${ef.SatO2}` : '',
          ef.hallazgos ? `Hallazgos: ${ef.hallazgos}` : ''
        ].filter(Boolean).join('\n');

      } else if (b.type==='list') {
        content.contentEditable = "true";
        const arr = Array.isArray(j[b.key]) ? j[b.key] : [];
        content.textContent = arr.map(x=>`- ${x}`).join('\n');

      } else if (b.type==='orders') {
        content.contentEditable = "true";
        const arr = Array.isArray(j[b.key]) ? j[b.key] : [];
        content.textContent = arr.map(o=>`- ${o?.detalle||''}`).join('\n');

      } else if (b.type==='antecedentes') {
        content.contentEditable = "true";
        content.textContent = fmtAntecedentesToText(j.antecedentes||{});

      } else if (b.type==='ros') {
        content.contentEditable = "true";
        content.textContent = fmtROSToText(j.revision_sistemas||{});
      }

      card.appendChild(content);
      root.appendChild(card);
    }

    $('#btnSaveBlocks').onclick = () => {
      let jcur = {};
      try { jcur = JSON.parse($('#jsonClinicoBox').value||'{}'); } catch {}
      const nodes = root.querySelectorAll('.hc-content');
      nodes.forEach(n=>{
        const k = n.dataset.key;
        const val = n.textContent.trim();

        if (k==='examen_fisico'){
          const ef = {};
          val.split('\n').forEach(line=>{
            const m = line.split(':');
            if (m.length>=2){
              const key = m[0].trim().toUpperCase();
              const v = m.slice(1).join(':').trim();
              if (key==='TA') ef.TA = v;
              if (key==='FC') ef.FC = v;
              if (key==='FR') ef.FR = v;
              if (key==='TEMP') ef.Temp = v;
              if (key==='SATO2') ef.SatO2 = v;
              if (key.toLowerCase()==='hallazgos') ef.hallazgos = v;
            }
          });
          jcur.examen_fisico = ef;

        } else if (k==='impresion_dx' || k==='alertas') {
          jcur[k] = val.split('\n').map(s=>s.replace(/^\-\s?/, '').trim()).filter(Boolean);

        } else if (k==='ordenes' || k==='recetas') {
          jcur[k] = val.split('\n').map(s=>{
            const d = s.replace(/^\-\s?/, '').trim();
            return d ? {detalle:d} : null;
          }).filter(Boolean);

        } else if (k==='antecedentes') {
          jcur.antecedentes = parseAntecedentesFromText(val);

        } else if (k==='revision_sistemas') {
          jcur.revision_sistemas = parseROSFromText(val);

        } else {
          jcur[k] = val;
        }
      });

      // Compactar EA
      if (jcur.enfermedad_actual) jcur.enfermedad_actual = compactEA(jcur.enfermedad_actual);

      // Mezclar datos del formulario de paciente
      jcur = mergePatientIntoJson(jcur);

      $('#jsonClinicoBox').value = JSON.stringify(jcur, null, 2);
      renderHistoriaClinica(jcur);
      log('💾 HC actualizada desde bloques + datos paciente.');
    };
  }

  // -------- Extractor UI (fallback) --------
  function extractAntecedentesRosFromTranscript(transcript){
    const T = (Array.isArray(transcript)?transcript:[])
      .map(t => (t?.text||'').toLowerCase())
      .join(' . ');

    const has = (w) => T.includes(w);
    const pick = (cond, text) => { if (cond) return text; return null; };

    const antecedentes = {};
    const meds = [];
    if (T.includes('losart')) meds.push('Losartán');
    if (T.includes('furosemida')) meds.push('Furosemida');
    if (T.includes('ibuprofeno')) meds.push('Ibuprofeno (reciente)');
    if (meds.length) (antecedentes.farmacologicos = meds);

    const pers = [];
    if (has('hipertens')) pers.push('Hipertensión arterial');
    if (has('cardiopat')) pers.push('Cardiopatía');
    if (pers.length) antecedentes.personales = pers;

    if (has('sin alerg') || has('no alerg')) antecedentes.alergias = ['Sin alergias conocidas'];

    const ros = {};
    const resp = [
      pick(has('tos'), 'Tos'),
      pick(has('disnea') || has('falta de aire') || has('ahog'), 'Disnea'),
    ].filter(Boolean);
    if (resp.length) ros.respiratorio = resp;

    const cardio = [
      pick(has('palpitaciones') || has('rápido'), 'Palpitaciones'),
      pick(has('edema') || has('hinchazón') || has('tobillos'), 'Edema maleolar')
    ].filter(Boolean);
    if (cardio.length) ros.cardiovascular = cardio;

    const gu = [
      pick(has('orino menos') || has('orino poco') || has('diuresis'), 'Diuresis disminuida')
    ].filter(Boolean);
    if (gu.length) ros.genitourinario = gu;

    if (!('neurologico' in ros)) ros.neurologico = 'Sin cefalea intensa ni déficit';
    if (!('dermatologico' in ros)) ros.dermatologico = 'Sin exantemas';

    const ef = {};
    const ta = T.match(/ta\s*(\d{2,3}\s*\/\s*\d{2,3})/i);
    if (ta) ef.TA = ta[1].replace(/\s/g,'');
    const fc = T.match(/fc\s*(\d{2,3})/i);
    if (fc) ef.FC = fc[1];
    const fr = T.match(/fr\s*(\d{2,3})/i);
    if (fr) ef.FR = fr[1];
    const temp = T.match(/(\b3[5-9](?:[.,]\d+)?)\s*°?c/);
    if (temp) ef.Temp = temp[1].replace(',','.');
    const sato2 = T.match(/sato2\s*(\d{2,3})/i);
    if (sato2) ef.SatO2 = sato2[1];

    return { antecedentes, revision_sistemas: ros, examen_fisico: ef };
  }

  // -------- Sugerencias --------
  function renderSuggestions(sugs){
    const panel = document.querySelector('#cdsPanel'); panel.innerHTML = '';
    if (!Array.isArray(sugs) || sugs.length===0){
      panel.innerHTML = '<span class="tiny text-gray-500">Sin sugerencias para este caso.</span>';
      return;
    }
    const inferActions = (s) => {
      const acts = new Set(Array.isArray(s.actions) ? s.actions : []);
      const looksDrug = /(?:\bmg\b|\bml\b|\bvo\b|\biv\b|\bim\b|cada\s+\d+)/i.test(s.proposed || s.message || '');
      const type = (s.type || '').toLowerCase();
      if (type.includes('medication') || looksDrug) acts.add('add');
      if ((type.includes('alternative') || type.includes('medication')) && (s.proposed && s.current)) acts.add('replace');
      return Array.from(acts);
    };

    const addOrder = (detail) => {
      let jcur = {};
      try { jcur = JSON.parse($('#jsonClinicoBox').value||'{}'); } catch {}
      jcur.ordenes = Array.isArray(jcur.ordenes) ? jcur.ordenes : [];
      jcur.ordenes.push({detalle: detail});
      $('#jsonClinicoBox').value = JSON.stringify(jcur, null, 2);
      renderBlocks(jcur); renderHistoriaClinica(jcur);
      log('➕ Orden agregada:', detail);
    };

    const addRx = (detail) => {
      let jcur = {};
      try { jcur = JSON.parse($('#jsonClinicoBox').value||'{}'); } catch {}
      jcur.recetas = Array.isArray(jcur.recetas) ? jcur.recetas : [];
      jcur.recetas.push({detalle: detail});
      $('#jsonClinicoBox').value = JSON.stringify(jcur, null, 2);
      renderBlocks(jcur); renderHistoriaClinica(jcur);
      log('💊 Receta agregada:', detail);
    };

    const replaceRx = (currentTxt, proposedTxt) => {
      let jcur = {};
      try { jcur = JSON.parse($('#jsonClinicoBox').value||'{}'); } catch {}
      let changed = false;
      if (Array.isArray(jcur.recetas)) {
        jcur.recetas = jcur.recetas.map(r=>{
          const d = (r && r.detalle || '');
          if (currentTxt && d.toLowerCase().includes(currentTxt.toLowerCase())) {
            changed = true; return {detalle: proposedTxt};
          }
          return r;
        });
      }
      if (!changed) {
        jcur.recetas = Array.isArray(jcur.recetas) ? jcur.recetas : [];
        jcur.recetas.push({detalle: proposedTxt});
      }
      $('#jsonClinicoBox').value = JSON.stringify(jcur, null, 2);
      renderBlocks(jcur); renderHistoriaClinica(jcur);
      log(changed ? `🔁 Reemplazado: ${currentTxt} → ${proposedTxt}` : `➕ Añadido (no había match): ${proposedTxt}`);
    };

    sugs.forEach((s, idx)=>{
      const id   = s.id || `sug-${idx}`;
      const type = (s.type || 'info').toUpperCase();
      const text = s.message || s.proposed || '(sin detalle)';
      const pmids = Array.isArray(s.pmids) ? s.pmids : [];
      const notes = Array.isArray(s.safety_notes) ? s.safety_notes : [];
      const actions = inferActions(s);
      const current = s.current || '';
      const proposed= s.proposed || '';

      const card = document.createElement('div');
      card.className='bg-white shadow-md rounded-lg p-4 border border-blue-200 sug mb-4';
      card.innerHTML = `
        <div class="flex justify-between items-center mb-1">
          <b class="text-blue-700 uppercase text-sm">${type}</b>
          <span class="tiny text-gray-500">ID: ${id}</span>
        </div>
        <div class="text-gray-800 mb-2">${text}</div>
        ${s.rationale ? `<div class="tiny italic text-gray-600">${s.rationale}</div>` : ''}
        ${pmids.length ? `<div class="tiny text-gray-600 mt-2">
            Evidencia:<br>${pmids.slice(0,5).map(p=>`• <a target="_blank" href="https://pubmed.ncbi.nlm.nih.gov/${p}/" class="hover:underline">PubMed ${p}</a>`).join('<br/>')}
          </div>` : '' }
        ${notes.length ? `<div class="tiny text-gray-600 mt-2">
            Notas de seguridad:<br>${notes.map(n=>`• ${n}`).join('<br/>')}
          </div>` : '' }
        <div class="mt-4 flex gap-3 flex-wrap"></div>
      `;
      const btnBar = card.querySelector('div.mt-4');

      if (actions.includes('add')) {
        const bAdd = document.createElement('button');
        bAdd.className = 'px-3 py-1 text-sm rounded-lg font-medium primary hover:bg-blue-600';
        bAdd.textContent = `Agregar ${s.proposed ? 'receta' : 'orden'}`;
        bAdd.onclick = () => {
          const payload = s.proposed || s.message || '';
          if (/mg|ml|vo|im|iv|cada\s+\d/i.test(payload)) addRx(payload);
          else addOrder(payload);
        };
        btnBar.appendChild(bAdd);
      }
      if (actions.includes('replace') && current && proposed) {
        const bRep = document.createElement('button');
        bRep.className = 'px-3 py-1 text-sm rounded-lg font-medium bg-blue-500 text-white hover:bg-blue-600';
        bRep.textContent = `Reemplazar ${current} → ${proposed}`;
        bRep.onclick = () => replaceRx(current, proposed);
        btnBar.appendChild(bRep);
      }
      const bIgnore = document.createElement('button');
      bIgnore.className = 'px-3 py-1 text-sm rounded-lg font-medium bg-gray-200 hover:bg-gray-300';
      bIgnore.textContent = 'Ignorar';
      bIgnore.onclick = () => { card.remove(); log('🚫 Sugerencia ignorada:', id); };
      btnBar.appendChild(bIgnore);

      panel.appendChild(card);
    });
  }

  // -------- Vista legible --------
  function safeUnit(v, unit) {
    if (v == null) return null;
    const t = String(v).toLowerCase().trim();
    if (t.includes(unit.toLowerCase())) return v;
    if (unit === 'mmHg' && (t.includes('sobre') || t.includes('/'))) return v;
    if (unit === '°C'  && (t.includes('°') || t.includes('grados'))) return v;
    if ((unit === 'lpm' || unit === 'rpm') && (t.includes('lpm') || t.includes('rpm') || t.includes('x'))) return v;
    return v + ' ' + unit;
  }
  function renderHistoriaClinica(j) {
    j = j || {};
    const ef = j.examen_fisico || {};

    function formatEA(ea) {
      if (!ea) return "(sin dato)";
      if (typeof ea === 'string') return ea;
      if (typeof ea === 'object') {
        const parts = [];
        if (ea.inicio) parts.push("Inicio: " + ea.inicio);
        if (ea.evolucion) parts.push("Evolución: " + ea.evolucion);
        if (ea.sintomas) parts.push("Síntomas: " + ea.sintomas);
        if (ea.descripcion) parts.push(ea.descripcion);
        if (ea.texto) parts.push(ea.texto);
        return parts.length > 0 ? parts.join("\n") : JSON.stringify(ea, null, 2);
      }
      return String(ea);
    }

    function formatAntecedentes(A) {
      if (!A || typeof A!=='object') return "- (sin datos)";
      const line = (key, arr) => {
        const v = Array.isArray(arr) ? arr.join('; ') : (typeof arr==='string' ? arr : '');
        return v ? `• ${key}: ${v}` : null;
      };
      const rows = [
        line('Personales', A.personales),
        line('Patológicos', A.patologicos),
        line('Farmacológicos', A.farmacologicos),
        line('Alergias', A.alergias),
        line('Hábitos', A.habitos),
      ].filter(Boolean);
      return rows.length ? rows.join("\n") : "- (sin datos)";
    }

    function formatROS(ros) {
      if (!ros || typeof ros!=='object') return "- (sin datos)";
      const out = [];
      for (const [sistema, val] of Object.entries(ros)) {
        if (Array.isArray(val)) out.push(`• ${sistema}: ${val.join('; ')}`);
        else if (typeof val==='string') out.push(`• ${sistema}: ${val}`);
      }
      return out.length ? out.join('\n') : "- (sin datos)";
    }

    const vitalsLines = [];
    if (ef.TA)   vitalsLines.push("Tensión arterial: " + safeUnit(ef.TA, "mmHg"));
    if (ef.FC)   vitalsLines.push("Frecuencia cardíaca: " + safeUnit(ef.FC, "lpm"));
    if (ef.FR)   vitalsLines.push("Frecuencia respiratoria: " + safeUnit(ef.FR, "rpm"));
    if (ef.Temp) vitalsLines.push("Temperatura: " + safeUnit(ef.Temp, "°C"));

    let t = "";
    t += "MOTIVO DE CONSULTA\n" + (j.motivo_consulta || "(sin dato)") + "\n\n";
    t += "3. ENFERMEDAD ACTUAL\n" + formatEA(j.enfermedad_actual) + "\n\n";

    t += "4. ANTECEDENTES MÉDICOS PERSONALES\n";
    t += formatAntecedentes(j.antecedentes) + "\n\n";

    t += "5. REVISIÓN POR SISTEMAS\n";
    t += formatROS(j.revision_sistemas) + "\n\n";

    t += "6. EXAMEN FÍSICO\n";
    t += (vitalsLines.length ? vitalsLines.join("\n") + "\n" : "- (sin datos)\n");
    if (ef.hallazgos) t += "Hallazgos: " + ef.hallazgos + "\n";

    t += "\n7. IMPRESIÓN DIAGNÓSTICA\n";
    const imp = (j.impresion_dx || []);
    t += (imp.length ? imp.map(d=> "• " + d).join("\n") : "- (sin datos)") + "\n\n";

    t += "8. PLAN DE MANEJO (ÓRDENES)\n";
    const ords = (j.ordenes || []);
    t += (ords.length ? ords.map(o=> "• " + (o?.detalle || "(sin detalle)")).join("\n") : "- (sin datos)") + "\n\n";

    t += "9. RECETAS\n";
    const recs = (j.recetas || []);
    t += (recs.length ? recs.map(r=> "• " + (r?.detalle || "(sin detalle)")).join("\n") : "- (sin datos)") + "\n\n";

    t += "10. ALERTAS\n";
    const al = (j.alertas || []);
    t += (al.length ? al.map(a=> "• " + a).join("\n") : "- (ninguna)");

    $('#hcView').textContent = t;
  }

  // -------- Botones principales --------
  $('#btnStart').onclick = startRecording;
  $('#btnPause').onclick = pauseRecording;
  $('#btnResume').onclick = resumeRecording;
  $('#btnStop').onclick = stopRecording;
  $('#btnUpload').onclick = doIngest;
  $('#btnGen').onclick = doGenerate;
  $('#btnPushApi').onclick = pushViaApi;
  $('#btnPushHapi').onclick = pushDirectHapi;

  $('#audioPreview').onloadeddata = () => { $('#btnUpload').disabled = false; log('🎵 Audio cargado y listo para subir'); };
  $('#transcriptBox').addEventListener('input', () => { log('📝 Transcript modificado manualmente'); });
  $('#encounterId').value = '';

  // Guardar datos paciente → JSON clínico
  $('#btnSavePatient').onclick = () => {
    let jcur = {};
    try { jcur = JSON.parse($('#jsonClinicoBox').value||'{}'); } catch {}
    jcur = mergePatientIntoJson(jcur);
    $('#jsonClinicoBox').value = JSON.stringify(jcur, null, 2);
    renderHistoriaClinica(jcur);
    renderBlocks(jcur);
    log('💾 Datos de paciente guardados en JSON.');
  };

  log('✅ UI lista. Pasos:');
  log('1) Llena Datos del paciente y presiona "Guardar en JSON".');
  log('2) (Opcional) Graba y sube audio. ');
  log('3) Genera historia con "/nlp/generate".');
  log('4) Imprime con "Imprimir historia (local)".');

  // ---- Pushers ----
  async function pushViaApi(){
    const apiBase=$('#apiBase').value.trim();
    let bundle; try{ bundle=JSON.parse($('#bundleBox').value||'{}'); }catch{ setText('#pushMsg','Bundle inválido (JSON)','err'); return; }
    setText('#pushMsg','Pushing via API...','warn');
    try{
      const resp=await fetch(`${apiBase}/fhir/push`,{ method:'POST', headers:{'Content-Type':'application/fhir+json'}, body:JSON.stringify(bundle) });
      const text=await resp.text();
      if(!resp.ok){ setText('#pushMsg',`Error ${resp.status}`,'err'); log('❌ /fhir/push:', text); return; }
      const data=JSON.parse(text); setText('#pushMsg','OK (API)','ok'); log('📦 push via API OK', data);
    }catch(e){ setText('#pushMsg',`Error: ${e}`,'err'); log('❌ push via API:', e); }
  }
  async function pushDirectHapi(){
    const hapiBase=$('#hapiBase').value.trim();
    let bundle; try{ bundle=JSON.parse($('#bundleBox').value||'{}'); }catch{ setText('#pushMsg','Bundle inválido (JSON)','err'); return; }
    setText('#pushMsg','Pushing directo...','warn');
    try{
      const resp=await fetch(hapiBase,{ method:'POST', headers:{'Content-Type':'application/fhir+json'}, body:JSON.stringify(bundle) });
      const text=await resp.text();
      if(!resp.ok){ setText('#pushMsg',`Error ${resp.status}`,'err'); log('❌ push HAPI:', text); return; }
      const data=JSON.parse(text); setText('#pushMsg','OK (HAPI)','ok'); log('📦 push directo HAPI OK', data);
    }catch(e){ setText('#pushMsg',`Error: ${e}`,'err'); log('❌ push HAPI:', e); }
  }
})();

// ====== Impresión ======
function getJsonClinicoFromUI() {
  try {
    const txt = document.getElementById('jsonClinicoBox')?.value || '{}';
    const j = JSON.parse(txt);
    return (j && typeof j === 'object') ? j : {};
  } catch { return {}; }
}
function asListLines(arr, bullet = '•') {
  if (!Array.isArray(arr) || arr.length === 0) return '<div class="muted">—</div>';
  return `<ul>${arr.map(x => `<li>${bullet} ${typeof x === 'string' ? x : (x?.detalle || JSON.stringify(x))}</li>`).join('')}</ul>`;
}
function makePrintableHTML(json) {
  const j = json || {};
  const ef = j.examen_fisico || {};
  const vitals = [
    ef.TA    ? `<div><b>TA:</b> ${ef.TA}</div>`     : '',
    ef.FC    ? `<div><b>FC:</b> ${ef.FC}</div>`     : '',
    ef.FR    ? `<div><b>FR:</b> ${ef.FR}</div>`     : '',
    ef.Temp  ? `<div><b>Temp:</b> ${ef.Temp} °C</div>` : '',
    ef.SatO2 ? `<div><b>SatO₂:</b> ${ef.SatO2}%</div>` : '',
  ].filter(Boolean).join('') || '<div class="muted">—</div>';

  function formatEA(ea) {
    if (!ea) return '<div class="muted">—</div>';
    if (typeof ea === 'string') return `<div>${ea}</div>`;
    const parts = [];
    if (ea.inicio)      parts.push(`<div><b>Inicio:</b> ${ea.inicio}</div>`);
    if (ea.evolucion)   parts.push(`<div><b>Evolución:</b> ${ea.evolucion}</div>`);
    if (ea.sintomas)    parts.push(`<div><b>Síntomas:</b> ${ea.sintomas}</div>`);
    if (ea.descripcion) parts.push(`<div>${ea.descripcion}</div>`);
    if (ea.texto)       parts.push(`<div>${ea.texto}</div>`);
    return parts.join('') || `<pre>${JSON.stringify(ea, null, 2)}</pre>`;
  }

  // Encabezado desde JSON (paciente.*)
  const nom   = j.paciente?.nombre || j.nombre_paciente || '—';
  const tipo  = j.paciente?.identificacion?.tipo || '—';
  const num   = j.paciente?.identificacion?.numero || j.documento || '—';
  const fnac  = j.paciente?.fecha_nacimiento || '—';
  const edad  = j.edad || '—';
  const sexo  = j.sexo || '—';
  const dir   = j.paciente?.direccion || '—';
  const tel   = j.paciente?.telefono || '—';
  const eps   = j.paciente?.eps || '—';

  return `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<title>Historia Clínica</title>
<style>
  :root { color-scheme: light; }
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }
  h1,h2 { margin: 0 0 8px 0; }
  h1 { font-size: 1.6rem; }
  h2 { font-size: 1.05rem; margin-top: 18px; border-bottom: 1px solid #e2e2e2; padding-bottom: 4px; }
  .muted { color: #666; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }
  .box { border: 1px solid #e6e6e6; border-radius: 10px; padding: 12px; background: #fafafa; }
  .sm { font-size: .9rem; }
  ul { margin: 6px 0 0 18px; }
  .head { display:flex; justify-content: space-between; gap: 12px; align-items:flex-start; }
  .head .left { font-weight: 600; }
  .head .right { text-align: right; }
  .foot { margin-top: 24px; font-size: .85rem; color: #666; }
  @media print {
    body { margin: 8mm 10mm; }
    .noprint { display: none !important; }
    .box { page-break-inside: avoid; }
  }
</style>
</head>
<body>
  <div class="head">
    <div class="left">
      Institución / IPS<br/>
      <span class="sm">Consulta General</span>
    </div>
    <div class="right sm">
      <div><b>Profesional:</b> Dr./Dra. Prueba</div>
      <div><b>Registro:</b> RP/TP: —</div>
      <div><b>Fecha:</b> ${new Date().toLocaleString()}</div>
    </div>
  </div>

  <h1>Historia Clínica</h1>

  <h2>1. Identificación del paciente</h2>
  <div class="box grid">
    <div><b>Nombre:</b> ${nom}</div>
    <div><b>Tipo y número de identificación:</b> ${tipo} ${num}</div>
    <div><b>Fecha de nacimiento:</b> ${fnac}</div>
    <div><b>Edad:</b> ${edad}</div>
    <div><b>Sexo:</b> ${sexo}</div>
    <div><b>Dirección:</b> ${dir}</div>
    <div><b>Teléfono:</b> ${tel}</div>
    <div><b>EPS:</b> ${eps}</div>
  </div>

  <h2>2. Motivo de consulta</h2>
  <div class="box">${j.motivo_consulta || '<span class="muted">—</span>'}</div>

  <h2>3. Enfermedad actual</h2>
  <div class="box">${formatEA(j.enfermedad_actual)}</div>

  <h2>4. Antecedentes</h2>
  <div class="box grid">
    <div><b>Personales:</b> ${asListLines(j.antecedentes?.personales || [])}</div>
    <div><b>Patológicos:</b> ${asListLines(j.antecedentes?.patologicos || [])}</div>
    <div><b>Farmacológicos:</b> ${asListLines(j.antecedentes?.farmacologicos || [])}</div>
    <div><b>Alergias:</b> ${asListLines(j.antecedentes?.alergias || [])}</div>
    <div><b>Hábitos:</b> ${asListLines(j.antecedentes?.habitos || [])}</div>
  </div>

  <h2>5. Revisión por sistemas</h2>
  <div class="box">${
    (() => {
      const ros = j.revision_sistemas || {};
      if (!ros || typeof ros !== 'object' || Object.keys(ros).length === 0) return '<div class="muted">—</div>';
      const lines = Object.entries(ros).map(([k,v]) => {
        const txt = Array.isArray(v) ? v.join('; ') : (typeof v === 'string' ? v : JSON.stringify(v));
        return `<div>• <b>${k}:</b> ${txt}</div>`;
      }).join('');
      return lines || '<div class="muted">—</div>';
    })()
  }</div>

  <h2>6. Examen físico</h2>
  <div class="box grid">
    <div>${[
      ef.TA    ? `<div><b>TA:</b> ${ef.TA}</div>`     : '',
      ef.FC    ? `<div><b>FC:</b> ${ef.FC}</div>`     : '',
      ef.FR    ? `<div><b>FR:</b> ${ef.FR}</div>`     : '',
      ef.Temp  ? `<div><b>Temp:</b> ${ef.Temp} °C</div>` : '',
      ef.SatO2 ? `<div><b>SatO₂:</b> ${ef.SatO2}%</div>` : '',
    ].filter(Boolean).join('') || '<div class="muted">—</div>'}</div>
    ${ef.hallazgos ? `<div><b>Hallazgos:</b> ${ef.hallazgos}</div>` : ''}
    ${j.imc ? `<div><b>IMC:</b> ${j.imc}</div>` : ''}
  </div>

  <h2>7. Impresión diagnóstica</h2>
  <div class="box">${asListLines(j.impresion_dx || [])}</div>

  <h2>8. Plan de manejo / Órdenes</h2>
  <div class="box">${asListLines(j.ordenes || [])}</div>

  <h2>9. Prescripciones</h2>
  <div class="box">${asListLines(j.recetas || [])}</div>

  <h2>10. Alertas</h2>
  <div class="box">${asListLines(j.alertas || [])}</div>

  <div class="foot"><div>Documento generado electrónicamente.</div></div>

  <div class="noprint" style="margin-top:16px;">
    <button onclick="window.print()" style="padding:8px 12px;">🖨️ Imprimir</button>
  </div>
</body>
</html>`;
}
function openPrintableFromUI() {
  // Antes de imprimir, mezclamos los datos del formulario en el JSON (por si el usuario no le dio "Guardar en JSON")
  let j = getJsonClinicoFromUI();
  // replicamos el merge del app (versión rápida):
  try {
    const p = {
      nombre_paciente: document.getElementById('patientName')?.value.trim(),
      identificacion: {
        tipo: document.getElementById('idType')?.value.trim(),
        numero: document.getElementById('idNumber')?.value.trim()
      },
      fecha_nacimiento: document.getElementById('dob')?.value.trim(),
      edad: document.getElementById('age')?.value.trim(),
      sexo: document.getElementById('sex')?.value.trim(),
      direccion: document.getElementById('address')?.value.trim(),
      telefono: document.getElementById('phone')?.value.trim(),
      eps: document.getElementById('eps')?.value.trim()
    };
    if (!j.paciente) j.paciente = {};
    if (p.nombre_paciente) j.paciente.nombre = p.nombre_paciente;
    if (p.identificacion?.tipo || p.identificacion?.numero) {
      j.paciente.identificacion = {
        ...(j.paciente.identificacion||{}),
        ...p.identificacion
      };
    }
    if (p.fecha_nacimiento) j.paciente.fecha_nacimiento = p.fecha_nacimiento;
    if (p.edad) j.edad = p.edad;
    if (p.sexo) j.sexo = p.sexo;
    if (p.direccion) j.paciente.direccion = p.direccion;
    if (p.telefono) j.paciente.telefono = p.telefono;
    if (p.eps) j.paciente.eps = p.eps;
  } catch {}
  const html = makePrintableHTML(j);

  const w = window.open('', '_blank');
  if (w) {
    w.document.open(); w.document.write(html); w.document.close();
    setTimeout(() => { try { w.focus(); w.print(); } catch {} }, 200);
    return;
  }

  // Fallback overlay
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed; inset:0; z-index:999999; background:white; display:flex; flex-direction:column;';
  const bar = document.createElement('div');
  bar.style.cssText = 'padding:8px 12px; background:#111; color:#fff; display:flex; justify-content:space-between; align-items:center; font:14px/1.2 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;';
  bar.innerHTML = `<div>Vista de impresión</div>
    <div style="display:flex; gap:8px;">
      <button id="btnPrintNow" style="padding:6px 10px; background:#2563eb; color:white; border:0; border-radius:8px; cursor:pointer;">Imprimir</button>
      <button id="btnClosePrint" style="padding:6px 10px; background:#e11d48; color:white; border:0; border-radius:8px; cursor:pointer;">Cerrar</button>
    </div>`;
  const frame = document.createElement('iframe');
  frame.style.cssText = 'border:0; width:100%; height:100%; flex:1;';
  frame.srcdoc = html;
  overlay.appendChild(bar);
  overlay.appendChild(frame);
  document.body.appendChild(overlay);

  const printNow = () => { try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch {} };
  const closeView = () => { overlay.remove(); };

  bar.querySelector('#btnPrintNow').onclick = printNow;
  bar.querySelector('#btnClosePrint').onclick = closeView;
  frame.onload = () => { setTimeout(printNow, 150); };
}
document.getElementById('btnPrintLocal')?.addEventListener('click', openPrintableFromUI);

// ==== Catálogos ====
const EPS_CO = [
  // EPS del régimen contributivo y subsidiado (principales a nivel nacional)
  "SURA", "Sanitas", "Nueva EPS", "Salud Total", "Compensar", "Famisanar",
  "Coosalud", "Mutual SER", "Ambuq", "SOS (Comfandi)", "Comfenalco Valle",
  "Comfamiliar Huila", "Comfamiliar Risaralda", "Medimás (en transición)",
  "Aliansalud", "Ecoopsos", "Cafesalud (histórica)", "Asmet Salud",
  "Emdisalud", "DUSAKAWI", "Mallamas", "Capital Salud", "Saviasalud",
  "Emssanar", "Anas Wayuu", "Comparta"
];
// Puedes editar/depurar esta lista según tu realidad local.

// ==== Poblado del SELECT de EPS y manejo de “OTRA…” ====
function populateEPSSelect() {
  const sel = document.getElementById('eps');
  if (!sel) return;
  // Inserta EPS antes de la opción "OTRA"
  const otherIdx = Array.from(sel.options).findIndex(o => o.value === 'OTRA');
  const insertBefore = otherIdx >= 0 ? sel.options[otherIdx] : null;
  EPS_CO.forEach(name => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name;
    sel.insertBefore(opt, insertBefore);
  });

  const epsOther = document.getElementById('epsOther');
  sel.addEventListener('change', () => {
    if (sel.value === 'OTRA') {
      epsOther.classList.remove('hidden');
      epsOther.focus();
    } else {
      epsOther.classList.add('hidden');
      epsOther.value = '';
    }
  });
}
// Poblamos EPS una sola vez en carga:
populateEPSSelect();

// === Fecha de nacimiento → cálculo automático de edad ===
const dobInput = document.getElementById('dob');
const ageInput = document.getElementById('age');

if (dobInput && ageInput) {
  dobInput.addEventListener('change', () => {
    const val = dobInput.value;
    if (!val) return;
    const dob = new Date(val);
    const today = new Date();
    let edad = today.getFullYear() - dob.getFullYear();
    const m = today.getMonth() - dob.getMonth();
    if (m < 0 || (m === 0 && today.getDate() < dob.getDate())) edad--;
    ageInput.value = `${edad} años`;
  });
}