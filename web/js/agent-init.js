// ========== AGENT CHAT INITIALIZATION ==========
// Initialize clinical agent chat when the page loads

let clinicalAgent = null;
let agentUI = null;

// Function to initialize the agent
async function initializeAgent() {
    const apiBase = $('#apiBase').value.trim();
    const encounterId = $('#encounterId').value.trim() || makeEncounterId();
    $('#encounterId').value = encounterId;

    // Get patient context from form
    const patientContext = {
        age: $('#age').value.trim() || undefined,
        allergies: [], // Could extract from form if needed
        weight: undefined, // Could add weight field to form
    };

    try {
        // Create agent instance
        clinicalAgent = new ClinicalAgentChat(apiBase, encounterId);

        // Initialize with patient context
        await clinicalAgent.initialize(patientContext);

        // Create UI
        agentUI = new AgentChatUI('agentChatContainer', clinicalAgent);

        log('🤖 Agente clínico inicializado correctamente');
    } catch (error) {
        log('❌ Error inicializando agente:', error.message);
        // Show error in container
        const container = document.getElementById('agentChatContainer');
        if (container) {
            container.innerHTML = `
        <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
          <p class="text-sm text-yellow-800">
            <strong>⚠️ Agente no disponible</strong><br>
            El agente clínico requiere que el servidor esté corriendo.<br>
            Error: ${error.message}
          </p>
          <button onclick="initializeAgent()" class="mt-2 px-3 py-1 bg-yellow-600 text-white rounded hover:bg-yellow-700 text-sm">
            Reintentar
          </button>
        </div>
      `;
        }
    }
}

// Function to acknowledge alert (called from HTML)
window.acknowledgeAlert = async function (alertIndex) {
    if (!clinicalAgent) return;
    try {
        await clinicalAgent.acknowledgeAlert(alertIndex);
        log(`✓ Alerta ${alertIndex} reconocida`);
    } catch (error) {
        log(`❌ Error reconociendo alerta: ${error.message}`);
    }
};

// Initialize agent when encounter ID changes or when generate button is clicked
$('#btnGen').addEventListener('click', async () => {
    // First do the normal generation
    await doGenerate();

    // Then initialize/update agent if not already done
    if (!clinicalAgent) {
        setTimeout(() => initializeAgent(), 1000); // Wait a bit for generation to complete
    }
});

// Also allow manual initialization
const initAgentBtn = document.createElement('button');
initAgentBtn.textContent = '🤖 Inicializar Agente';
initAgentBtn.className = 'px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-sm';
initAgentBtn.onclick = initializeAgent;

// Add button to agent container initially
const agentContainer = document.getElementById('agentChatContainer');
if (agentContainer) {
    agentContainer.innerHTML = `
    <div class="text-center p-6">
      <p class="text-gray-600 mb-4">El agente clínico te ayudará durante la consulta con validación de medicamentos, razonamiento clínico y sugerencias basadas en evidencia.</p>
      <button onclick="initializeAgent()" class="px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 font-semibold">
        🤖 Inicializar Agente Clínico
      </button>
    </div>
  `;
}

log('✅ Sistema de agente clínico listo. Click en "Inicializar Agente Clínico" para comenzar.');
