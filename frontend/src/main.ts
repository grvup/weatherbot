// src/main.ts

// Assuming these imports exist in your frontend structure
import { startRecording, stopRecording, setAudioReadyHandler } from './recorder'; 
// Import both voice and text processing functions from api.ts
import { uploadAudio, pollForResult, processTextQuery } from './api'; 
import { isMediaRecorderSupported } from './recorder'; // Assuming this helper exists

// Define the structure for a message object
type ChatMessage = { sender: 'user' | 'bot', text: string, timestamp: string };

// --- 1. Get DOM Elements ---
const recordBtn = document.getElementById('recordBtn') as HTMLButtonElement;
const stopBtn = document.getElementById('stopBtn') as HTMLButtonElement;
const statusDiv = document.getElementById('status') as HTMLDivElement;
// Placeholder elements (used for cleanup/reference, but not for history display)
const aiSuggestion = document.getElementById('aiSuggestion') as HTMLDivElement; 
const queryInput = document.getElementById('queryInput') as HTMLInputElement;

// --- DOM Containers for Rendering ---
const outputSection = document.querySelector('.output-section') as HTMLElement;
const weatherInfoDiv = document.getElementById('weatherInfo') as HTMLDivElement;


// =========================================================================
// |                       CHAT HISTORY LOGIC (IN-MEMORY)                  |
// =========================================================================

/**
 * Stores all messages for the current session, resetting on page refresh.
 */
let currentChatHistory: ChatMessage[] = []; 

/**
 * Renders a single message object into the DOM.
 */
function renderMessage(message: ChatMessage): void {
    const isUser = message.sender === 'user';
    
    // Create the new message element structure
    const newMessageBubble = document.createElement('div');
    newMessageBubble.classList.add('message-bubble', isUser ? 'user-message' : 'bot-message');
    newMessageBubble.classList.remove('hidden'); 

    const messageParagraph = document.createElement('p');
    messageParagraph.textContent = message.text;
    
    if (message.sender === 'bot') {
        messageParagraph.classList.add('response-text');
    }

    newMessageBubble.appendChild(messageParagraph);

    // Insert the new message before the #weatherInfo div
    outputSection.insertBefore(newMessageBubble, weatherInfoDiv);
}

/**
 * Adds a new message to the in-memory array and renders it.
 */
function addAndSaveMessage(sender: 'user' | 'bot', text: string): void {
    // 1. Create new message object
    const newMessage: ChatMessage = { 
        sender: sender, 
        text: text, 
        timestamp: new Date().toISOString() 
    };
    
    // 2. Add to in-memory history
    currentChatHistory.push(newMessage);
    
    // 3. If this is the *first* message, remove the initial placeholder before rendering
    if (currentChatHistory.length === 1 && aiSuggestion) {
        aiSuggestion.remove();
    }
    
    // 4. Render the message to the DOM
    renderMessage(newMessage);

    // 5. Scroll to bottom
    outputSection.scrollTop = outputSection.scrollHeight;
}

// NOTE: loadChatHistory and saveChatHistory are now obsolete.

// =========================================================================


// --- 2. UI Helpers for State Management ---

function updateStatus(message: string, className: string = 'ready'): void {
    statusDiv.textContent = message;
    statusDiv.className = `status-message ${className}`;
}

function toggleRecordingButtons(isRecording: boolean): void {
    recordBtn.disabled = isRecording;
    stopBtn.disabled = !isRecording;
    queryInput.disabled = isRecording || !stopBtn.disabled;
}

function resetUI(): void {
    // This function now only resets the status and input field, not the chat history DOM.
    toggleRecordingButtons(false);
    updateStatus('🎙 Ready', 'ready');
    
    // Clear user input text
    queryInput.value = '';

    // Hide weather info (if applicable)
    weatherInfoDiv.classList.add('hidden');
}


// --- 3. Event Listeners ---

// Start Recording (Voice Input)
recordBtn.addEventListener('click', async () => {
    try {
        if (!isMediaRecorderSupported()) {
            updateStatus('❌ Browser does not support recording.', 'error');
            return;
        }
        
        resetUI(); 
        toggleRecordingButtons(true);
        updateStatus('🔴 Listening...', 'recording');
        
        await startRecording(); 
        
    } catch (e) {
        console.error("Recording start failed:", e);
        updateStatus('⚠️ Error: Mic access denied or failed.', 'error');
        toggleRecordingButtons(false);
    }
});

// Stop Recording (Voice Input)
stopBtn.addEventListener('click', () => {
    stopRecording(); 
    toggleRecordingButtons(false);
    updateStatus('...Processing voice command...', 'processing');
});


// Function to handle text input submission
async function handleTextSubmission() {
    const textQuery = queryInput.value.trim();
    if (!textQuery) return;

    // 1. Render User Query IMMEDIATELY
    addAndSaveMessage('user', textQuery);

    resetUI();
    toggleRecordingButtons(true); 
    updateStatus('...Processing text query...', 'processing');
    queryInput.value = textQuery; // Keep text in input temporarily

    try {
        const finalResult = await processTextQuery(textQuery); 
        const responseText = finalResult.response_text; 
        
        if (responseText) {
            // 2. Render Bot Response
            addAndSaveMessage('bot', responseText);
            updateStatus('✅ Done', 'ready');
        } else {
            const errorReason = finalResult.error || "No clear response.";
            const errorMsg = `Processing Error: ${errorReason}.`;
            // 2. Render Bot Error Message
            addAndSaveMessage('bot', errorMsg);
            updateStatus('❌ Error during processing', 'error');
        }

    } catch (error: any) {
        console.error("Text pipeline failed:", error);
        const errorMsg = `Fatal Error: ${error.message}.`;
        // 2. Render Bot Error Message
        addAndSaveMessage('bot', errorMsg);
        updateStatus('❌ Pipeline Failed', 'error');
    } finally {
        toggleRecordingButtons(false); 
        queryInput.value = ''; // Clear the input field after the cycle is complete
    }
}

// Event Listener for the Enter key on the input field (Text Input)
queryInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
        handleTextSubmission();
    }
});


// --- 4. Core Pipeline Logic (After Audio is Ready) ---

setAudioReadyHandler(async (audioBlob: Blob) => {
    let transcribedText = 'User query (voice) could not be transcribed.'; 
    
    try {
        const { trace_id } = await uploadAudio(audioBlob);

        const finalResult = await pollForResult(trace_id, 1500); 

        // Get transcription
        transcribedText = finalResult.text || transcribedText;
        const responseText = finalResult.response?.text;
        
        // 1. Render User Query IMMEDIATELY
        addAndSaveMessage('user', transcribedText);
        
        if (finalResult.status === 'done') {
            const finalBotText = responseText || "AI response generated, but text was empty.";
            // 2. Render Bot Response
            addAndSaveMessage('bot', finalBotText);
            updateStatus('✅ Done', 'ready');
        } else {
            const errorReason = finalResult.error || finalResult.warnings?.join('; ') || "Unknown failure.";
            const errorMsg = `Processing Error: ${errorReason}.`;
            // 2. Render Bot Error Message
            addAndSaveMessage('bot', errorMsg);
            updateStatus('❌ Error during processing', 'error');
        }

    } catch (error: any) {
        console.error("Full pipeline failed:", error);
        const errorMsg = `Fatal Error: ${error.message}.`;
        // Ensure user text is rendered before the error response if a failure occurs late
        if (currentChatHistory.length === 0 || currentChatHistory[currentChatHistory.length - 1].sender === 'bot') {
             addAndSaveMessage('user', transcribedText); 
        }
        // 2. Render Bot Error Message
        addAndSaveMessage('bot', errorMsg); 
        updateStatus('❌ Pipeline Failed', 'error');
    } finally {
        toggleRecordingButtons(false);
    }
});


// --- 5. Initialization ---

document.addEventListener('DOMContentLoaded', () => {
    toggleRecordingButtons(false); 
    updateStatus('🎙 Ready', 'ready');
    
    // No history loading is necessary.
    // The placeholder (#aiSuggestion) will remain until the first message is sent.
    
    console.log("Weather Assistant UI loaded.");
});