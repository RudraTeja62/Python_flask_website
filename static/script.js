const recordButton = document.getElementById('record');
const stopButton = document.getElementById('stop');
const audioElement = document.getElementById('audio');
const textToSpeechForm = document.getElementById('textToSpeechForm');
const textInput = document.getElementById('textInput');
const ttsAudio = document.getElementById('ttsAudio');
const timerDisplay = document.getElementById('timer');
const audioList = document.getElementById('audioList');
const ttsAudioList = document.getElementById('ttsAudioList');

let mediaRecorder;
let audioChunks = [];
let startTime;
let timerInterval;

// ✅ Start Recording Audio
recordButton.addEventListener('click', async () => {
    try {
        console.log("[INFO] Requesting microphone access...");
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });

        audioChunks = [];
        mediaRecorder.ondataavailable = event => {
            audioChunks.push(event.data);
        };

        mediaRecorder.start();
        startTime = Date.now();
        timerInterval = setInterval(() => {
            const elapsedTime = Math.floor((Date.now() - startTime) / 1000);
            timerDisplay.textContent = `Recording: ${formatTime(elapsedTime)}`;
        }, 1000);

        recordButton.disabled = true;
        stopButton.disabled = false;
        timerDisplay.textContent = "Recording...";

        console.log("[INFO] Recording started...");
    } catch (error) {
        console.error('[ERROR] Microphone access denied:', error);
        alert('Microphone access denied. Please enable permissions.');
    }
});

// ✅ Stop Recording & Upload
stopButton.addEventListener('click', () => {
    if (!mediaRecorder) {
        console.error("[ERROR] No active mediaRecorder found.");
        return;
    }

    mediaRecorder.stop();
    clearInterval(timerInterval);
    timerDisplay.textContent = "Processing...";

    mediaRecorder.onstop = async () => {
        console.log("[INFO] Recording stopped. Preparing file for upload...");

        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        const formData = new FormData();
        formData.append('audio_data', audioBlob, 'recorded_audio.webm');

        try {
            const response = await fetch('/upload', { method: 'POST', body: formData });
            const data = await response.json();

            console.log("[DEBUG] Upload Response:", data);

            if (data.error) {
                alert("Upload Error: " + data.error);
                return;
            }

            if (data.processed_file) {
                console.log("[INFO] Upload successful:", data.processed_file);
                const mp3File = data.processed_file;

                // ✅ Add Recorded Audio to List
                const newAudioItem = document.createElement('li');
                newAudioItem.innerHTML = `
                    <audio controls>
                        <source src="/uploads/${mp3File}" type="audio/mp3">
                        Your browser does not support the audio element.
                    </audio>
                    <br><strong>${mp3File}</strong>`;
                audioList.appendChild(newAudioItem);

                // ✅ Display Transcription
                if (data.transcription_file) {
                    const transcriptItem = document.createElement('pre');
                    transcriptItem.textContent = `Transcript: ${data.transcription_file}`;
                    newAudioItem.appendChild(transcriptItem);
                }

                // ✅ Show Sentiment Analysis
                if (data.sentiment_analysis_file) {
                    const sentimentLink = document.createElement('a');
                    sentimentLink.href = `/uploads/${data.sentiment_analysis_file}`;
                    sentimentLink.target = '_blank';
                    sentimentLink.textContent = 'Download Sentiment Analysis';
                    newAudioItem.appendChild(sentimentLink);
                }

                timerDisplay.textContent = "Recording saved!";
            } else {
                console.error("[ERROR] Upload response missing file info.");
                alert("Upload failed. No file received from server.");
            }
        } catch (error) {
            console.error('[ERROR] Upload failed:', error);
            alert('Failed to upload the audio.');
        }
    };

    recordButton.disabled = false;
    stopButton.disabled = true;
});

// ✅ Text-to-Speech Conversion
textToSpeechForm.addEventListener('submit', async (event) => {
    event.preventDefault();

    const text = textInput.value.trim();
    if (!text) {
        alert("Please enter text to convert to speech.");
        return;
    }

    try {
        const response = await fetch('/text_to_speech', {
            method: 'POST',
            body: new FormData(textToSpeechForm)
        });

        const data = await response.json();

        console.log("[DEBUG] TTS Response:", data);

        if (data.error) {
            alert("TTS Error: " + data.error);
            return;
        }

        if (data.tts_audio) {
            console.log("[INFO] Text-to-Speech successful:", data.tts_audio);

            // ✅ Add Generated TTS Audio to List
            const ttsItem = document.createElement('li');
            ttsItem.innerHTML = `
                <audio controls>
                    <source src="/tts/${data.tts_audio}" type="audio/mp3">
                    Your browser does not support the audio element.
                </audio>
                <br><strong>${data.tts_audio}</strong>`;
            ttsAudioList.appendChild(ttsItem);

            // ✅ Show Sentiment Analysis
            if (data.sentiment_file) {
                const sentimentLink = document.createElement('a');
                sentimentLink.href = `/tts/${data.sentiment_file}`;
                sentimentLink.target = '_blank';
                sentimentLink.textContent = 'Download Sentiment Analysis';
                ttsItem.appendChild(sentimentLink);
            }
        } else {
            console.error("[ERROR] TTS response missing file info.");
            alert("Text-to-Speech conversion failed.");
        }
    } catch (error) {
        console.error('[ERROR] Text-to-Speech error:', error);
        alert('Failed to process Text-to-Speech.');
    }
});

// ✅ Format Time Display
function formatTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
}
