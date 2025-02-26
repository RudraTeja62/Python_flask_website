import os
import subprocess
import soundfile as sf
import noisereduce as nr
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
from google.cloud import speech, texttospeech, language_v1
from datetime import datetime

# Initialize Flask application
app = Flask(__name__)
app.secret_key = "secure_random_key"

# Create directories for storing uploaded and generated files
UPLOAD_FOLDER = 'uploads'
TTS_FOLDER = 'tts'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TTS_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TTS_FOLDER'] = TTS_FOLDER

# Set up Google Cloud API clients
speech_client = speech.SpeechClient()
tts_client = texttospeech.TextToSpeechClient()
language_client = language_v1.LanguageServiceClient()

# Define supported file formats
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'webm'}

def is_audio_file(filename):
    """Verify if the uploaded file has a supported extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def webm_to_wav(source_path):
    """Convert WebM files to WAV format using FFmpeg."""
    output_wav = source_path.replace('.webm', '.wav')
    try:
        subprocess.run(['ffmpeg', '-i', source_path, '-ac', '1', '-ar', '16000', output_wav], check=True)
        os.remove(source_path)  # Remove original WebM file after conversion
        return output_wav
    except Exception as error:
        print(f"[ERROR] WebM to WAV conversion failed: {error}")
        return None

def wav_to_mp3(source_path):
    """Convert WAV files to MP3 format using FFmpeg."""
    output_mp3 = source_path.replace('.wav', '.mp3')
    try:
        subprocess.run(['ffmpeg', '-i', source_path, '-ac', '1', '-ar', '16000', '-b:a', '128k', output_mp3], check=True)
        return output_mp3
    except Exception as error:
        print(f"[ERROR] WAV to MP3 conversion failed: {error}")
        return None

def remove_background_noise(audio_path):
    """Reduce noise in an audio file using noise reduction."""
    try:
        audio_data, sample_rate = sf.read(audio_path, dtype='float32')
        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)  # Convert stereo to mono
        clean_audio = nr.reduce_noise(y=audio_data, sr=sample_rate, y_noise=audio_data[:sample_rate])
        sf.write(audio_path, clean_audio, sample_rate)
    except Exception as error:
        print(f"[WARNING] Noise reduction unsuccessful: {error}")

def analyze_text_sentiment(text):
    """Perform sentiment analysis on text using Google NLP API."""
    document = language_v1.Document(content=text, type_=language_v1.Document.Type.PLAIN_TEXT)
    sentiment_result = language_client.analyze_sentiment(request={'document': document})

    score = sentiment_result.document_sentiment.score
    magnitude = sentiment_result.document_sentiment.magnitude

    # Categorizing sentiment score
    if score > 0.25:
        sentiment_label = "Positive"
    elif score < -0.25:
        sentiment_label = "Negative"
    else:
        sentiment_label = "Neutral"

    return sentiment_label, score, magnitude

@app.route('/')
def homepage():
    """Render the main page listing available audio and generated files."""
    recorded_files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('.mp3')]
    tts_generated_files = [f for f in os.listdir(TTS_FOLDER) if f.endswith('.mp3')]
    return render_template('index.html', audio_files=recorded_files, tts_files=tts_generated_files)

@app.route('/upload', methods=['POST'])
def handle_audio_upload():
    """Handle user audio uploads, convert formats, and process speech recognition."""
    if 'audio_data' not in request.files:
        return jsonify({'error': 'No audio data received'}), 400

    file = request.files['audio_data']
    if file.filename == '' or not is_audio_file(file.filename):
        return jsonify({'error': 'Invalid file type or empty file name'}), 400

    filename = secure_filename(f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.webm")
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)

    print(f"[INFO] File uploaded: {file_path}")

    # Convert uploaded file to WAV format
    wav_file = webm_to_wav(file_path)
    if not wav_file:
        return jsonify({'error': 'Audio conversion error'}), 500

    remove_background_noise(wav_file)
    mp3_file = wav_to_mp3(wav_file)
    if not mp3_file:
        return jsonify({'error': 'MP3 conversion error'}), 500

    # Perform speech-to-text processing
    try:
        with open(wav_file, 'rb') as audio_content:
            content = audio_content.read()
        audio_input = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code="en-US"
        )
        response = speech_client.recognize(config=config, audio=audio_input)

        if not response.results:
            print("[ERROR] No speech detected.")
            return jsonify({'error': 'No speech detected'}), 500

        transcript = "\n".join(result.alternatives[0].transcript for result in response.results)
        transcript_path = wav_file.replace('.wav', '.txt')
        with open(transcript_path, 'w') as text_file:
            text_file.write(transcript)

        print(f"[INFO] Transcript saved: {transcript}")

        # Sentiment Analysis
        sentiment_label, score, magnitude = analyze_text_sentiment(transcript)
        sentiment_path = transcript_path.replace('.txt', '_sentiment.txt')
        with open(sentiment_path, 'w') as sentiment_file:
            sentiment_file.write(f"Text: {transcript}\n")
            sentiment_file.write(f"Sentiment: {sentiment_label}\n")
            sentiment_file.write(f"Score: {score}\n")
            sentiment_file.write(f"Magnitude: {magnitude}\n")

        return jsonify({
            'processed_file': os.path.basename(mp3_file),
            'transcription_file': os.path.basename(transcript_path),
            'sentiment': sentiment_label,
            'sentiment_analysis_file': os.path.basename(sentiment_path)
        }), 200

    except Exception as e:
        print(f"[ERROR] Speech-to-Text Processing Failed: {e}")
        return jsonify({'error': 'Speech recognition failed'}), 500

@app.route('/text_to_speech', methods=['POST'])
def convert_text_to_speech():
    """Convert user-provided text to speech using Google TTS API."""
    text_content = request.form.get('text', '')
    if not text_content:
        return jsonify({'error': 'Text input missing'}), 400

    sentiment_label, score, magnitude = analyze_text_sentiment(text_content)

    tts_input = texttospeech.SynthesisInput(text=text_content)
    voice_config = texttospeech.VoiceSelectionParams(language_code="en-US", ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

    tts_response = tts_client.synthesize_speech(input=tts_input, voice=voice_config, audio_config=audio_config)

    if not tts_response.audio_content:
        print("[ERROR] Google TTS API returned empty response.")
        return jsonify({'error': 'Text-to-Speech conversion failed'}), 500

    tts_filename = f"tts_{datetime.now().strftime('%Y%m%d-%H%M%S')}.mp3"
    tts_path = os.path.join(TTS_FOLDER, tts_filename)

    with open(tts_path, 'wb') as output_audio:
        output_audio.write(tts_response.audio_content)

    return jsonify({'tts_audio': tts_filename, 'sentiment_file': tts_filename.replace('.mp3', '_sentiment.txt')})

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded audio files."""
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/tts/<filename>')
def tts_file(filename):
    """Serve generated text-to-speech files."""
    return send_from_directory(TTS_FOLDER, filename)

if __name__ == '__main__':
    print("[INFO] Starting Flask application on port 8080...")
    app.run(host='0.0.0.0', port=8080, debug=True)
