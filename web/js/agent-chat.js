/**
 * Clinical Agent Chat Module
 * Provides interactive chat with the clinical AI agent
 */

class ClinicalAgentChat {
    constructor(apiBase, encounterId) {
        this.apiBase = apiBase;
        this.encounterId = encounterId;
        this.messages = [];
        this.alerts = [];
    }

    /**
     * Initialize agent for current encounter
     */
    async initialize(patientContext = {}) {
        try {
            const response = await fetch(`${this.apiBase}/agent/initialize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    encounter_id: this.encounterId,
                    patient_id: patientContext.patient_id || null,
                    patient_context: patientContext
                })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            console.log('Agent initialized:', data);
            return data;
        } catch (error) {
            console.error('Failed to initialize agent:', error);
            throw error;
        }
    }

    /**
     * Send a message to the agent
     */
    async sendMessage(speaker, text) {
        try {
            const response = await fetch(`${this.apiBase}/agent/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    encounter_id: this.encounterId,
                    speaker: speaker,
                    text: text,
                    auto_extract: true
                })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();

            // Store message
            this.messages.push({
                speaker: speaker,
                text: text,
                timestamp: new Date().toISOString()
            });

            // Update alerts
            if (data.alerts && data.alerts.length > 0) {
                this.alerts.push(...data.alerts);
            }

            return data;
        } catch (error) {
            console.error('Failed to send message:', error);
            throw error;
        }
    }

    /**
     * Get clinical reasoning for a query
     */
    async getClinicalReasoning(query, usePubmed = true) {
        try {
            const response = await fetch(`${this.apiBase}/agent/clinical-reasoning`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    encounter_id: this.encounterId,
                    query: query,
                    use_pubmed: usePubmed
                })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error('Failed to get clinical reasoning:', error);
            throw error;
        }
    }

    /**
     * Validate a prescription
     */
    async validatePrescription(medications) {
        try {
            const response = await fetch(`${this.apiBase}/agent/validate-prescription`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    encounter_id: this.encounterId,
                    medications: medications
                })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error('Failed to validate prescription:', error);
            throw error;
        }
    }

    /**
     * Get suggested next steps
     */
    async getNextSteps() {
        try {
            const response = await fetch(`${this.apiBase}/agent/suggest-next-steps`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ encounter_id: this.encounterId })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error('Failed to get next steps:', error);
            throw error;
        }
    }

    /**
     * Get active alerts
     */
    async getAlerts() {
        try {
            const response = await fetch(`${this.apiBase}/agent/alerts/${this.encounterId}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            this.alerts = data.alerts || [];
            return this.alerts;
        } catch (error) {
            console.error('Failed to get alerts:', error);
            throw error;
        }
    }

    /**
     * Acknowledge an alert
     */
    async acknowledgeAlert(alertIndex) {
        try {
            const response = await fetch(`${this.apiBase}/agent/alerts/${this.encounterId}/acknowledge`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ alert_index: alertIndex })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            this.alerts = data.alerts || [];
            return data;
        } catch (error) {
            console.error('Failed to acknowledge alert:', error);
            throw error;
        }
    }

    /**
     * Get conversation summary
     */
    async getSummary() {
        try {
            const response = await fetch(`${this.apiBase}/agent/summary/${this.encounterId}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error('Failed to get summary:', error);
            throw error;
        }
    }

    /**
     * Update patient context
     */
    async updatePatientContext(context) {
        try {
            const response = await fetch(`${this.apiBase}/agent/update-patient-context`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    encounter_id: this.encounterId,
                    patient_context: context
                })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error('Failed to update patient context:', error);
            throw error;
        }
    }
}

/**
 * UI Helper for rendering agent chat
 */
class AgentChatUI {
    constructor(containerId, agent) {
        this.container = document.getElementById(containerId);
        this.agent = agent;
        this.setupUI();
    }

    setupUI() {
        if (!this.container) return;

        this.container.innerHTML = `
            <div class="agent-chat-container">
                <div class="agent-messages" id="agentMessages" style="max-height: 400px; overflow-y: auto; border: 1px solid #e5e7eb; border-radius: 0.5rem; padding: 1rem; margin-bottom: 1rem; background: #f9fafb;">
                    <p class="text-sm text-gray-500">El agente clínico está listo. Escribe un mensaje para comenzar.</p>
                </div>
                
                <div class="agent-alerts" id="agentAlerts" style="margin-bottom: 1rem;"></div>
                
                <div class="agent-input" style="display: flex; gap: 0.5rem;">
                    <select id="agentSpeaker" class="p-2 border rounded-lg bg-white" style="width: 120px;">
                        <option value="DOCTOR">DOCTOR</option>
                        <option value="PACIENTE">PACIENTE</option>
                    </select>
                    <input type="text" id="agentInput" placeholder="Escribe aquí..." class="flex-1 p-2 border rounded-lg" />
                    <button id="agentSend" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">Enviar</button>
                </div>
                
                <div class="agent-actions mt-3" style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                    <button id="btnAgentReasoning" class="px-3 py-1 text-sm bg-purple-100 text-purple-700 rounded-lg hover:bg-purple-200">🧠 Razonamiento</button>
                    <button id="btnAgentNextSteps" class="px-3 py-1 text-sm bg-green-100 text-green-700 rounded-lg hover:bg-green-200">➡️ Próximos pasos</button>
                    <button id="btnAgentValidate" class="px-3 py-1 text-sm bg-orange-100 text-orange-700 rounded-lg hover:bg-orange-200">✓ Validar receta</button>
                </div>
            </div>
        `;

        this.messagesContainer = document.getElementById('agentMessages');
        this.alertsContainer = document.getElementById('agentAlerts');
        this.input = document.getElementById('agentInput');
        this.speakerSelect = document.getElementById('agentSpeaker');
        this.sendButton = document.getElementById('agentSend');

        this.setupEventListeners();
    }

    setupEventListeners() {
        this.sendButton.addEventListener('click', () => this.sendMessage());
        this.input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.sendMessage();
        });

        document.getElementById('btnAgentReasoning')?.addEventListener('click', () => this.showReasoning());
        document.getElementById('btnAgentNextSteps')?.addEventListener('click', () => this.showNextSteps());
        document.getElementById('btnAgentValidate')?.addEventListener('click', () => this.validatePrescription());
    }

    async sendMessage() {
        const text = this.input.value.trim();
        if (!text) return;

        const speaker = this.speakerSelect.value;
        this.input.value = '';

        // Add to UI immediately
        this.addMessage(speaker, text);

        try {
            const result = await this.agent.sendMessage(speaker, text);

            // Show extracted info
            if (result.extracted_info) {
                this.addSystemMessage('Información extraída: ' + JSON.stringify(result.extracted_info, null, 2));
            }

            // Show suggestions
            if (result.suggestions && result.suggestions.length > 0) {
                this.addSystemMessage('💡 Sugerencias: ' + result.suggestions.map(s => s.message).join('; '));
            }

            // Show alerts
            if (result.alerts && result.alerts.length > 0) {
                this.renderAlerts(result.alerts);
            }
        } catch (error) {
            this.addSystemMessage('❌ Error: ' + error.message, 'error');
        }
    }

    addMessage(speaker, text) {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'mb-2 p-2 rounded-lg ' + (speaker === 'DOCTOR' ? 'bg-blue-50' : 'bg-green-50');
        msgDiv.innerHTML = `<strong class="text-sm">${speaker}:</strong> <span class="text-sm">${text}</span>`;
        this.messagesContainer.appendChild(msgDiv);
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    addSystemMessage(text, type = 'info') {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'mb-2 p-2 rounded-lg ' + (type === 'error' ? 'bg-red-50 text-red-700' : 'bg-gray-100 text-gray-700');
        msgDiv.innerHTML = `<span class="text-xs font-mono">${text}</span>`;
        this.messagesContainer.appendChild(msgDiv);
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    renderAlerts(alerts) {
        this.alertsContainer.innerHTML = '';
        alerts.forEach((alert, index) => {
            const alertDiv = document.createElement('div');
            const severityClass = alert.severity === 'critical' ? 'bg-red-100 border-red-400 text-red-800' : 'bg-yellow-100 border-yellow-400 text-yellow-800';
            alertDiv.className = `p-3 border-l-4 rounded ${severityClass} mb-2`;
            alertDiv.innerHTML = `
                <div class="flex justify-between items-start">
                    <div>
                        <strong class="text-sm">${alert.message}</strong>
                        ${alert.details ? `<p class="text-xs mt-1">${alert.details}</p>` : ''}
                    </div>
                    <button onclick="acknowledgeAlert(${index})" class="text-xs px-2 py-1 bg-white rounded hover:bg-gray-50">OK</button>
                </div>
            `;
            this.alertsContainer.appendChild(alertDiv);
        });
    }

    async showReasoning() {
        const query = prompt('¿Qué quieres que analice el agente?');
        if (!query) return;

        try {
            const result = await this.agent.getClinicalReasoning(query, true);
            this.addSystemMessage('🧠 Razonamiento:\n' + JSON.stringify(result.reasoning, null, 2));
            if (result.evidence && result.evidence.length > 0) {
                this.addSystemMessage('📚 Evidencia: ' + result.evidence.length + ' artículos encontrados');
            }
        } catch (error) {
            this.addSystemMessage('❌ Error: ' + error.message, 'error');
        }
    }

    async showNextSteps() {
        try {
            const result = await this.agent.getNextSteps();
            if (result.next_steps && result.next_steps.length > 0) {
                const steps = result.next_steps.map((s, i) => `${i + 1}. [${s.priority}] ${s.step}`).join('\n');
                this.addSystemMessage('➡️ Próximos pasos:\n' + steps);
            }
        } catch (error) {
            this.addSystemMessage('❌ Error: ' + error.message, 'error');
        }
    }

    async validatePrescription() {
        // This would need to extract medications from the current clinical JSON
        this.addSystemMessage('⚠️ Función de validación: implementar extracción de medicamentos del JSON clínico');
    }
}

// Export for use in main app
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ClinicalAgentChat, AgentChatUI };
}
