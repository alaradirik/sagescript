import os
import io
import math
import subprocess
import tempfile
from typing import  List

from pydub import AudioSegment


def split_audio(audio_path: str, chunk_duration: int = 600) -> List[str]:
    """
    Split audio file into chunks of specified duration.
    
    Args:
        audio_path: Path to the audio file
        chunk_duration: Duration of each chunk in seconds (default: 600s = 10 minutes)
    
    Returns:
        List of paths to audio chunks
    """
    # Load audio file
    audio = AudioSegment.from_file(audio_path)
    
    # Calculate number of chunks needed
    total_duration = len(audio) / 1000  # Convert to seconds
    num_chunks = math.ceil(total_duration / chunk_duration)
    
    chunk_paths = []
    temp_dir = tempfile.mkdtemp()
    
    # Split audio into chunks
    for i in range(num_chunks):
        start_time = i * chunk_duration * 1000  # Convert to milliseconds
        end_time = min((i + 1) * chunk_duration * 1000, len(audio))
        
        chunk = audio[start_time:end_time]
        chunk_path = os.path.join(temp_dir, f"chunk_{i}.wav")
        chunk.export(chunk_path, format="wav")
        chunk_paths.append(chunk_path)
    
    return chunk_paths


def preprocess_audio(input_file) -> str:
    """
    Preprocess audio file to match Groq's requirements (16kHz mono).
    """
    temp_dir = tempfile.gettempdir()
    output_file = os.path.join(temp_dir, "processed_audio.wav")

    # Convert to AudioSegment
    audio_bytes = input_file.read()
    audio_segment = AudioSegment.from_wav(io.BytesIO(audio_bytes))
    
    # Resample to 16kHz and save to file
    audio_segment = audio_segment.set_frame_rate(16000)
    audio_segment.export(output_file, format="wav")

    return output_file
