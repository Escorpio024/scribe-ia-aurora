// Finish Consultation Handler
// Handles ending the current consultation and preparing for the next patient

document.addEventListener('DOMContentLoaded', function () {
  const btnFinish = document.getElementById('btnFinishConsultation');

  if (btnFinish) {
    btnFinish.addEventListener('click', showFinishConfirmation);
  }
});

function showFinishConfirmation() {
  // Get current patient data
  // Try to get from currentPatient (Queue System) first, then fallback to admissionData
  const currentPatientJson = localStorage.getItem('currentPatient');
  const admissionDataJson = localStorage.getItem('admissionData');

  let patientName = 'Paciente';
  let data = null;

  if (currentPatientJson) {
    const currentPatient = JSON.parse(currentPatientJson);
    patientName = currentPatient.patient?.nombre || 'Paciente';
    data = currentPatient;
  } else if (admissionDataJson) {
    const admissionData = JSON.parse(admissionDataJson);
    patientName = admissionData.paciente?.nombre || 'Paciente';
    data = admissionData;
  } else {
    // No active consultation - go directly to pending
    window.location.href = 'pending.html';
    return;
  }

  // Create custom confirmation modal
  const modal = document.createElement('div');
  modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.7); display: flex; align-items: center; justify-content: center; z-index: 9999; animation: fadeIn 0.2s ease;';

  modal.innerHTML = `
    <div style="background: white; border-radius: 1.5rem; padding: 2rem; max-width: 500px; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3); animation: slideUp 0.3s ease;">
      <div style="text-align: center; margin-bottom: 1.5rem;">
        <div style="font-size: 3rem; margin-bottom: 0.5rem;">⚠️</div>
        <h2 style="font-size: 1.5rem; font-weight: 700; color: #111827; margin-bottom: 0.5rem;">
          ¿Finalizar Consulta?
        </h2>
        <p style="color: #6b7280; font-size: 0.875rem;">
          Paciente: <strong>${patientName}</strong>
        </p>
      </div>
      
      <div style="background: #f3f4f6; padding: 1rem; border-radius: 0.75rem; margin-bottom: 1.5rem;">
        <p style="font-size: 0.875rem; color: #4b5563; margin: 0;">
          <strong>Esto hará lo siguiente:</strong><br><br>
          ✅ Guardará la historia clínica actual<br>
          📥 Descargará el archivo JSON<br>
          🧹 Limpiará todos los campos<br>
          📋 Te llevará a la lista de pendientes
        </p>
      </div>
      
      <div style="display: flex; gap: 1rem;">
        <button id="btnCancelFinish" style="flex: 1; padding: 0.75rem 1.5rem; border: 2px solid #e5e7eb; background: white; color: #6b7280; border-radius: 0.75rem; font-weight: 600; cursor: pointer; transition: all 0.2s;">
          Cancelar
        </button>
        <button id="btnConfirmFinish" style="flex: 1; padding: 0.75rem 1.5rem; border: none; background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); color: white; border-radius: 0.75rem; font-weight: 600; cursor: pointer; transition: all 0.2s;">
          Sí, Finalizar
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(modal);

  // Add event listeners
  document.getElementById('btnCancelFinish').addEventListener('click', () => {
    document.body.removeChild(modal);
  });

  document.getElementById('btnConfirmFinish').addEventListener('click', () => {
    document.body.removeChild(modal);
    finishConsultation(data, patientName);
  });

  // Add animations
  if (!document.getElementById('finish-modal-styles')) {
    const style = document.createElement('style');
    style.id = 'finish-modal-styles';
    style.textContent = `
      @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
      }
      @keyframes slideUp {
        from { transform: translateY(20px); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
      }
    `;
    document.head.appendChild(style);
  }
}

async function finishConsultation(data, patientName) {
  // Show loading state
  const btnFinish = document.getElementById('btnFinishConsultation');
  const originalText = btnFinish.textContent;
  btnFinish.textContent = '⏳ Finalizando...';
  btnFinish.disabled = true;

  try {
    // 1. Save/Export current clinical history
    await saveCurrentHistory(data);

    // 2. Update Queue Status if using QueueManager
    if (window.QueueManager && data.id && data.id.startsWith('queue_')) {
      const queueManager = new window.QueueManager();
      queueManager.updatePatientStatus(data.id, 'completed');
    }

    // 3. Show success message
    showFinishSuccessMessage(patientName);

    // 4. Clear all data after a short delay
    setTimeout(() => {
      clearConsultationData();

      // 5. Redirect to pending list for next patient
      window.location.href = 'pending.html';
    }, 2000);

  } catch (error) {
    console.error('Error finalizando consulta:', error);
    alert('Error al finalizar la consulta. Por favor intenta de nuevo.');
    btnFinish.textContent = originalText;
    btnFinish.disabled = false;
  }
}

async function saveCurrentHistory(admissionData) {
  // Get current clinical JSON
  const jsonClinicoBox = document.getElementById('jsonClinicoBox');
  const clinicalData = jsonClinicoBox?.value ? JSON.parse(jsonClinicoBox.value) : {};

  // Get FHIR bundle
  const bundleBox = document.getElementById('bundleBox');
  const fhirBundle = bundleBox?.value ? JSON.parse(bundleBox.value) : {};

  // Create complete consultation record
  const consultationRecord = {
    admission: admissionData,
    clinical_data: clinicalData,
    fhir_bundle: fhirBundle,
    finished_at: new Date().toISOString(),
    encounter_id: admissionData.encounter_id
  };

  // Save to localStorage history
  saveToHistory(consultationRecord);

  // Download as JSON file
  downloadConsultationRecord(consultationRecord);

  console.log('✅ Historia clínica guardada:', consultationRecord);
}

function saveToHistory(record) {
  // Get existing history
  const historyJson = localStorage.getItem('consultationHistory');
  const history = historyJson ? JSON.parse(historyJson) : [];

  // Add new record
  history.push(record);

  // Keep only last 50 consultations
  if (history.length > 50) {
    history.shift();
  }

  // Save back
  localStorage.setItem('consultationHistory', JSON.stringify(history));
}

function downloadConsultationRecord(record) {
  // Handle both data structures (Queue vs Direct Admission)
  const patientName = (record.admission.patient?.nombre || record.admission.paciente?.nombre || 'Paciente').replace(/\s+/g, '_');
  const date = new Date().toISOString().split('T')[0];
  const filename = `historia_${patientName}_${date}.json`;

  const blob = new Blob([JSON.stringify(record, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);

  console.log(`📥 Historia descargada: ${filename}`);
}

function showFinishSuccessMessage(patientName) {
  // Create success overlay
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.8); display: flex; align-items: center; justify-content: center; z-index: 9999; animation: fadeIn 0.3s ease;';

  overlay.innerHTML = `
    <div style="background: white; border-radius: 1.5rem; padding: 3rem; max-width: 500px; text-align: center; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3); animation: slideUp 0.3s ease;">
      <div style="font-size: 4rem; margin-bottom: 1rem;">✅</div>
      <h2 style="font-size: 1.5rem; font-weight: 700; color: #111827; margin-bottom: 0.5rem;">
        Consulta Finalizada
      </h2>
      <p style="color: #6b7280; margin-bottom: 1.5rem;">
        Historia clínica de <strong>${patientName}</strong> guardada exitosamente
      </p>
      <div style="background: #f3f4f6; padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem;">
        <p style="font-size: 0.875rem; color: #4b5563;">
          📥 Archivo descargado<br>
          💾 Guardado en historial local<br>
          📋 Volviendo a lista de pendientes...
        </p>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  // Add animations
  const style = document.createElement('style');
  style.textContent = `
    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    @keyframes slideUp {
      from { transform: translateY(20px); opacity: 0; }
      to { transform: translateY(0); opacity: 1; }
    }
  `;
  document.head.appendChild(style);
}

function clearConsultationData() {
  // Clear admission data
  localStorage.removeItem('admissionData');
  localStorage.removeItem('currentPatient'); // Clear current queue patient

  // Clear all form fields
  const fields = [
    'patientName', 'idType', 'idNumber', 'dob', 'age', 'sex',
    'address', 'phone', 'eps', 'epsOther',
    'transcriptBox', 'jsonClinicoBox', 'bundleBox'
  ];

  fields.forEach(fieldId => {
    const field = document.getElementById(fieldId);
    if (field) {
      if (field.tagName === 'SELECT') {
        field.selectedIndex = 0;
      } else {
        field.value = '';
      }
    }
  });

  // Clear displays
  const displays = ['hcBlocks', 'cdsPanel', 'hcView'];
  displays.forEach(displayId => {
    const display = document.getElementById(displayId);
    if (display) {
      display.innerHTML = '';
    }
  });

  // Clear audio
  const audioPreview = document.getElementById('audioPreview');
  if (audioPreview) {
    audioPreview.src = '';
  }

  console.log('🧹 Datos de consulta limpiados');
}

// Export for use in other scripts
window.consultationFinisher = {
  finish: finishConsultation,
  clear: clearConsultationData
};
