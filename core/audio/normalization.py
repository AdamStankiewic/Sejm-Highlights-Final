"""
Audio normalization using EBU R128 standard
Part of Highlights AI Platform - Core Engine
"""
import subprocess
from pathlib import Path
from typing import Dict, Any


class AudioNormalizer:
    """Normalize audio loudness using EBU R128 broadcast standard"""

    def __init__(self, target_loudness: float = -16.0, sample_rate: int = 16000, channels: int = 1):
        self.target_loudness = target_loudness
        self.sample_rate = sample_rate
        self.channels = channels

    def normalize(self, input_path: str, output_path: str) -> Dict[str, Any]:
        """
        Normalize audio to target loudness using EBU R128

        Args:
            input_path: Path to input audio
            output_path: Path for normalized output

        Returns:
            Dict with normalization results
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        # Two-pass normalization using loudnorm filter
        cmd = [
            'ffmpeg',
            '-i', str(input_path),
            '-af', f'loudnorm=I={self.target_loudness}:LRA=11:TP=-1.5',
            '-ar', str(self.sample_rate),
            '-ac', str(self.channels),
            '-y',
            str(output_path)
        ]

        try:
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            return {
                'success': True,
                'output_path': str(output_path),
                'target_loudness': self.target_loudness
            }

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffmpeg normalization error: {e.stderr.decode()}")
