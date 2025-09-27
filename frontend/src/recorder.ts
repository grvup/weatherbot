// src/recorder.ts (Example implementation)

let mediaRecorder: MediaRecorder | null = null;
let audioChunks: Blob[] = [];
let stream: MediaStream | null = null;

// --- Callbacks for Main/UI ---
export type AudioHandler = (audioBlob: Blob) => void;
let onAudioReady: AudioHandler | null = null;

export function setAudioReadyHandler(handler: AudioHandler) {
    onAudioReady = handler;
}

/**
 * 1. Request microphone access and set up the recorder.
 */
export async function startRecording(): Promise<void> {
    try {
        // Request microphone access
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        // Event handler to collect audio data as it comes in
        mediaRecorder.ondataavailable = event => {
            audioChunks.push(event.data);
        };

        // Event handler when recording is stopped
        mediaRecorder.onstop = () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            if (onAudioReady) {
                onAudioReady(audioBlob); // Pass the final Blob back to main.ts
            }
            // Stop the microphone stream tracks
            stream?.getTracks().forEach(track => track.stop());
            stream = null;
        };

        // Start recording
        mediaRecorder.start();
        console.log("Recording started.");
    } catch (error) {
        console.error("Microphone access failed:", error);
        alert("Microphone access denied or failed. Check permissions.");
        throw error;
    }
}

/**
 * 2. Stop the recording.
 */
export function stopRecording(): void {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        console.log("Recording stopped.");
    }
}

/**
 * Check if the browser supports media recording.
 */
export function isMediaRecorderSupported(): boolean {
    return !!(navigator.mediaDevices && window.MediaRecorder);
}