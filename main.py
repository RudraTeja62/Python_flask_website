import os
from flask import Flask, request, redirect, flash, url_for, render_template
from werkzeug.utils import secure_filename
from google.cloud import speech, texttospeech
from datetime import datetime
from flask import send_from_directory

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Configure upload folders
UPLOAD_FOLDER = 'uploads'
TTS_FOLDER = 'tts'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TTS_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TTS_FOLDER'] = TTS_FOLDER

# Initialize Google Cloud clients
speech_client = speech.SpeechClient()
tts_client = texttospeech.TextToSpeechClient()

@app.route('/')
def index():
    # List uploaded files and TTS files
    files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if f.endswith('.wav')]
    tts_files = [f for f in os.listdir(app.config['TTS_FOLDER']) if f.endswith('.mp3')]
    
    # Check for existing transcripts (text files)
    transcripts = {}
    for file in files:
        txt_file = file.replace('.wav', '.txt')
        if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], txt_file)):
            transcripts[file] = txt_file

    return render_template('index.html', files=files, tts_files=tts_files, transcripts=transcripts)

@app.route('/upload', methods=['POST'])
def upload_audio():
    if 'audio_data' not in request.files:
        flash('No audio data provided')
        return redirect('/')
    
    file = request.files['audio_data']
    if file.filename == '':
        flash('No file selected')
        return redirect('/')

    if file:
        # Save the audio file
        filename = secure_filename(datetime.now().strftime("%Y%m%d-%I%M%S%p") + '.wav')
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Process with Google Speech-to-Text
        with open(file_path, 'rb') as audio_file:
            audio_content = audio_file.read()

        audio = speech.RecognitionAudio(content=audio_content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=48000,  
            language_code="en-US"
        )

        try:
            response = speech_client.recognize(config=config, audio=audio)

            # Debugging: Check if the response has results
            if not response.results:
                flash('No speech detected in the audio file.')
                print("Speech-to-Text returned no results.")
                return redirect('/')

            # Generate transcript
            transcript = '\n'.join(result.alternatives[0].transcript for result in response.results)

            # Debugging: print the transcript content
            print(f"Transcript: {transcript}")

            # Check if transcript is empty
            if not transcript.strip():
                flash('No transcript generated. Please try again.')
                return redirect('/')

            # Define the path for the transcript file
            transcript_path = file_path.replace('.wav', '.txt')

            # Write transcript to file
            with open(transcript_path, 'w') as transcript_file:
                transcript_file.write(transcript)

            flash('Audio processed and transcript generated.')
        except Exception as e:
            flash(f'Error processing the audio file: {str(e)}')
            print(f"Error processing audio: {e}")

    return redirect('/')

@app.route('/upload_text', methods=['POST'])
def upload_text():
    text = request.form.get('text', '')
    if not text:
        flash('No text provided')
        return redirect('/')

    # Process with Google Text-to-Speech
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )

    response = tts_client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )

    # Save the generated audio
    output_filename = datetime.now().strftime("%Y%m%d-%I%M%S%p") + '.mp3'
    output_path = os.path.join(app.config['TTS_FOLDER'], output_filename)
    with open(output_path, 'wb') as output_file:
        output_file.write(response.audio_content)

    flash('Text processed and audio generated.')
    return redirect('/')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    folder = app.config['UPLOAD_FOLDER'] if filename.endswith('.wav') else app.config['TTS_FOLDER']
    return send_from_directory(folder, filename)

if __name__ == '__main__':
    app.run(debug=True)
