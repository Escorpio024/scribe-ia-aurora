// Admission Data Loader
// Loads patient data from localStorage (Queue or Direct Admission) into the clinical interface

document.addEventListener('DOMContentLoaded', function () {
  loadAdmissionData();
});

function loadAdmissionData() {
  // Try to get data from Queue System first (currentPatient)
  // If not found, fallback to legacy admissionData (direct admission)
  const currentPatientJson = localStorage.getItem('currentPatient');
  const admissionDataJson = localStorage.getItem('admissionData');

  let data = null;
  let source = '';

  if (currentPatientJson) {
    const queueEntry = JSON.parse(currentPatientJson);
    // Map queue entry structure to expected format
    data = {
      paciente: queueEntry.patient,
      medico: queueEntry.doctor,
      fecha_admision: queueEntry.appointmentTime,
      encounter_id: queueEntry.encounter_id || queueEntry.id
    };
    source = 'Queue System';
  } else if (admissionDataJson) {
    data = JSON.parse(admissionDataJson);
    source = 'Direct Admission';
  }

  if (!data) {
    console.log('No admission data found');
    return;
  }

  console.log(`Loading admission data from ${source}:`, data);

  // 1. Fill Patient Demographics
  if (data.paciente) {
    const p = data.paciente;

    // Helper to fill and lock fields
    const fillAndLockField = (id, value) => {
      const field = document.getElementById(id);
      if (field) {
        field.value = value || '';
        field.readOnly = true;
        field.classList.add('bg-gray-50', 'cursor-not-allowed');
      }
    };

    // Helper for select fields
    const fillAndLockSelect = (id, value) => {
      const field = document.getElementById(id);
      if (field) {
        field.value = value || '';
        // For selects, we disable them to prevent changes
        // but we need to make sure the value is visible/selected
        field.disabled = true;
        field.classList.add('bg-gray-50', 'cursor-not-allowed');

        // Create a hidden input to submit the value if needed
        const hiddenInput = document.createElement('input');
        hiddenInput.type = 'hidden';
        hiddenInput.id = id + '_hidden';
        hiddenInput.value = value || '';
        field.parentNode.appendChild(hiddenInput);
      }
    };

    fillAndLockField('patientName', p.nombre);
    fillAndLockSelect('idType', p.identificacion?.tipo);
    fillAndLockField('idNumber', p.identificacion?.numero);
    fillAndLockField('dob', p.fecha_nacimiento);
    fillAndLockField('age', p.edad);
    fillAndLockSelect('sex', p.sexo);
    fillAndLockField('address', p.direccion);
    fillAndLockField('phone', p.telefono);

    // Handle EPS
    if (p.eps) {
      const epsSelect = document.getElementById('eps');
      // Check if the EPS is in the list
      let epsFound = false;
      for (let i = 0; i < epsSelect.options.length; i++) {
        if (epsSelect.options[i].value === p.eps) {
          epsFound = true;
          break;
        }
      }

      if (epsFound) {
        fillAndLockSelect('eps', p.eps);
      } else {
        fillAndLockSelect('eps', 'OTRA');
        const otherContainer = document.getElementById('epsOtherContainer');
        if (otherContainer) otherContainer.classList.remove('hidden');
        fillAndLockField('epsOther', p.eps);
      }
    }

    // Update Banner
    const bannerName = document.getElementById('bannerPatientName');
    const bannerId = document.getElementById('bannerPatientId');

    if (bannerName) bannerName.textContent = p.nombre;
    if (bannerId) bannerId.textContent = `${p.identificacion?.tipo} ${p.identificacion?.numero}`;
  }

  // 2. Fill Doctor Info
  if (data.medico) {
    const m = data.medico;
    const bannerDoc = document.getElementById('bannerDoctor');
    if (bannerDoc) bannerDoc.textContent = m.nombre;
  }

  // 3. Set Metadata
  if (data.encounter_id) {
    const encField = document.getElementById('encounterId');
    if (encField) {
      encField.value = data.encounter_id;
      encField.readOnly = true;
    }
  }

  // 4. Update UI State
  const btnSave = document.getElementById('btnSavePatient');
  if (btnSave) {
    btnSave.textContent = '✓ Datos Cargados';
    btnSave.disabled = true;
    btnSave.classList.add('bg-green-600', 'opacity-50', 'cursor-not-allowed');
    btnSave.classList.remove('bg-blue-600', 'hover:bg-blue-700');
  }

  // Show notification
  showNotification(`Paciente cargado: ${data.paciente?.nombre}`);
}

function showNotification(message) {
  const div = document.createElement('div');
  div.className = 'fixed bottom-4 right-4 bg-green-600 text-white px-6 py-3 rounded-lg shadow-lg z-50 fade-in';
  div.textContent = message;
  document.body.appendChild(div);

  setTimeout(() => {
    div.style.opacity = '0';
    setTimeout(() => div.remove(), 300);
  }, 3000);
}
