// Queue Manager - Patient Queue Management System
// Manages the patient queue for all doctors

class QueueManager {
    constructor() {
        this.queueKey = 'patientQueue';
    }

    // Add a new patient to the queue
    addPatient(patientData, doctorData, appointmentTime, reason = '') {
        const queue = this.getQueue();

        const queueEntry = {
            id: this.generateQueueId(),
            patient: patientData,
            doctor: doctorData,
            appointmentTime: appointmentTime,
            arrivalTime: new Date().toISOString(),
            status: 'pending', // pending, in_progress, completed
            priority: 'normal', // normal, urgent
            reason: reason,
            createdAt: new Date().toISOString(),
            startedAt: null,
            completedAt: null,
            encounter_id: this.generateEncounterId()
        };

        queue.push(queueEntry);
        this.saveQueue(queue);

        console.log('✅ Paciente agregado a la cola:', queueEntry);
        return queueEntry;
    }

    // Get all patients in queue
    getQueue() {
        const queueJson = localStorage.getItem(this.queueKey);
        return queueJson ? JSON.parse(queueJson) : [];
    }

    // Save queue to localStorage
    saveQueue(queue) {
        localStorage.setItem(this.queueKey, JSON.stringify(queue));
    }

    // Get patients for a specific doctor
    getPatientsByDoctor(doctorId, statusFilter = null) {
        const queue = this.getQueue();
        let filtered = queue.filter(entry => entry.doctor.id === doctorId);

        if (statusFilter) {
            filtered = filtered.filter(entry => entry.status === statusFilter);
        }

        // Sort by appointment time
        filtered.sort((a, b) => new Date(a.appointmentTime) - new Date(b.appointmentTime));

        return filtered;
    }

    // Get a specific patient by queue ID
    getPatientById(queueId) {
        const queue = this.getQueue();
        return queue.find(entry => entry.id === queueId);
    }

    // Update patient status
    updatePatientStatus(queueId, status) {
        const queue = this.getQueue();
        const entry = queue.find(e => e.id === queueId);

        if (entry) {
            entry.status = status;

            if (status === 'in_progress' && !entry.startedAt) {
                entry.startedAt = new Date().toISOString();
            } else if (status === 'completed' && !entry.completedAt) {
                entry.completedAt = new Date().toISOString();
            }

            this.saveQueue(queue);
            console.log(`✅ Estado actualizado: ${queueId} → ${status}`);
            return entry;
        }

        return null;
    }

    // Get next pending patient for a doctor
    getNextPatient(doctorId) {
        const pending = this.getPatientsByDoctor(doctorId, 'pending');
        return pending.length > 0 ? pending[0] : null;
    }

    // Remove a patient from queue
    removePatient(queueId) {
        let queue = this.getQueue();
        queue = queue.filter(entry => entry.id !== queueId);
        this.saveQueue(queue);
        console.log(`🗑️ Paciente removido de la cola: ${queueId}`);
    }

    // Get statistics for a doctor
    getDoctorStats(doctorId) {
        const allPatients = this.getPatientsByDoctor(doctorId);

        return {
            total: allPatients.length,
            pending: allPatients.filter(p => p.status === 'pending').length,
            inProgress: allPatients.filter(p => p.status === 'in_progress').length,
            completed: allPatients.filter(p => p.status === 'completed').length
        };
    }

    // Clear completed patients (cleanup)
    clearCompleted(doctorId = null) {
        let queue = this.getQueue();

        if (doctorId) {
            queue = queue.filter(entry =>
                !(entry.doctor.id === doctorId && entry.status === 'completed')
            );
        } else {
            queue = queue.filter(entry => entry.status !== 'completed');
        }

        this.saveQueue(queue);
        console.log('🧹 Pacientes completados limpiados');
    }

    // Generate unique queue ID
    generateQueueId() {
        return 'queue_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    // Generate encounter ID
    generateEncounterId() {
        const d = new Date();
        const pad = n => n.toString().padStart(2, '0');
        return `enc_${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
    }
}

// Doctor Session Manager
class DoctorSession {
    constructor() {
        this.sessionKey = 'currentDoctor';
    }

    // Login a doctor
    login(doctorData) {
        localStorage.setItem(this.sessionKey, JSON.stringify(doctorData));
        console.log('👨‍⚕️ Sesión iniciada:', doctorData.nombre);
        return doctorData;
    }

    // Logout current doctor
    logout() {
        localStorage.removeItem(this.sessionKey);
        localStorage.removeItem('currentPatient');
        console.log('👋 Sesión cerrada');
    }

    // Get current logged in doctor
    getCurrentDoctor() {
        const doctorJson = localStorage.getItem(this.sessionKey);
        return doctorJson ? JSON.parse(doctorJson) : null;
    }

    // Check if a doctor is logged in
    isLoggedIn() {
        return this.getCurrentDoctor() !== null;
    }

    // Get pending patients for current doctor
    getPendingPatients() {
        const doctor = this.getCurrentDoctor();
        if (!doctor) return [];

        const queueManager = new QueueManager();
        return queueManager.getPatientsByDoctor(doctor.id, 'pending');
    }

    // Set current patient being attended
    setCurrentPatient(queueEntry) {
        localStorage.setItem('currentPatient', JSON.stringify(queueEntry));

        // Update status to in_progress
        const queueManager = new QueueManager();
        queueManager.updatePatientStatus(queueEntry.id, 'in_progress');

        console.log('👤 Paciente en atención:', queueEntry.patient.nombre);
    }

    // Get current patient being attended
    getCurrentPatient() {
        const patientJson = localStorage.getItem('currentPatient');
        return patientJson ? JSON.parse(patientJson) : null;
    }

    // Clear current patient
    clearCurrentPatient() {
        localStorage.removeItem('currentPatient');
    }
}

// Export for use in other scripts
window.QueueManager = QueueManager;
window.DoctorSession = DoctorSession;
