// src/api.ts

// Set the base URL for your FastAPI backend
const BASE_URL = 'http://127.0.0.1:8000/api';

/**
 * 1. Uploads an audio Blob to the backend to start the processing.
 * @param audioBlob The recorded audio data.
 * @returns The trace_id to be used for polling.
 */
export async function uploadAudio(audioBlob: Blob): Promise<{ trace_id: string; status: string }> {
  const formData = new FormData();
  // The 'audio' key MUST match the FastAPI parameter name: audio: UploadFile = File(...)
  formData.append('audio', audioBlob, 'voice_query.wav');

  const response = await fetch(`${BASE_URL}/voice`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    // Attempt to parse JSON error detail from the backend
    let errorDetail = { detail: response.statusText };
    try {
        errorDetail = await response.json();
    } catch (e) {
        // Ignore JSON parsing errors if the response body is not JSON
    }
    throw new Error(`Audio upload failed: ${errorDetail.detail || response.statusText}`);
  }

  return response.json();
}

/**
 * 2. Polls the backend for the processing result (for voice queries).
 * @param traceId The ID returned from uploadAudio.
 * @returns The full result JSON, or a pending status.
 */
export async function getProcessingResult(traceId: string): Promise<any> {
  const response = await fetch(`${BASE_URL}/stt/${traceId}`);
  
  if (response.status === 404) {
      // Trace may not have been fully registered yet, treat as pending
      return { status: 'pending' }; 
  }

  if (!response.ok) {
    throw new Error('Failed to fetch processing result.');
  }

  return response.json();
}

/**
 * 3. Helper to repeatedly check the status until complete (for voice queries).
 */
export async function pollForResult(traceId: string, intervalMs: number = 1500): Promise<any> {
  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const result = await getProcessingResult(traceId);
        const status = result.status;

        // Check for 'done' or any status indicating failure
        if (status === 'done' || status === 'agent_done_chatbot_failed') {
          resolve(result);
        } else if (status && (status.includes('failed') || status.includes('error'))) {
          reject(new Error(`Processing failed. Status: ${status}`));
        } else {
          // Still pending/processing, poll again
          setTimeout(poll, intervalMs);
        }
      } catch (error) {
        reject(error);
      }
    };
    poll();
  });
}

// --- Text Query Endpoint ---

/**
 * Sends a plain text query to the backend for immediate processing.
 * @param textQuery The raw text input from the user.
 * @returns The immediate result containing response_text, NLU, and weather data.
 */
export async function processTextQuery(textQuery: string): Promise<any> {
  // Use URLSearchParams to safely encode the query parameter
  const params = new URLSearchParams({ query: textQuery });
  
  const response = await fetch(`${BASE_URL}/text?${params.toString()}`, {
    method: 'POST',
    // FastAPI expects the 'query' to be in the URL for the /api/text endpoint, 
    // so no body is sent.
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    let errorDetail = { detail: response.statusText };
    try {
        errorDetail = await response.json();
    } catch (e) {
        // Ignore JSON parsing errors
    }
    throw new Error(`Text query failed: ${errorDetail.detail || response.statusText}`);
  }

  return response.json();
}