"""
Setup script for Sejm Highlights AI Pipeline
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="sejm-highlights-ai",
    version="2.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Automated AI pipeline for generating highlights from Polish Parliament broadcasts",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/sejm-highlights-ai",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Multimedia :: Video",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.11",
    install_requires=[
        # Setuptools pinning (temporary workaround for ctranslate2 pkg_resources warning)
        # See: https://github.com/OpenNMT/CTranslate2/pull/1911
        "setuptools<81",

        # Core dependencies
        "numpy>=1.24.0",
        "scipy>=1.10.0",
        "PyYAML>=6.0",
        "python-dotenv>=1.0.0",
        
        # Audio/Video processing
        "librosa>=0.10.0",
        "soundfile>=0.12.0",
        
        # Deep Learning
        "torch>=2.0.0",
        "torchaudio>=2.0.0",
        
        # Speech Recognition
        "faster-whisper>=0.9.0",
        
        # NLP
        "spacy>=3.7.0",
        "transformers>=4.30.0",
        
        # YouTube
        "google-api-python-client>=2.100.0",
        "google-auth-oauthlib>=1.1.0",
        "google-auth-httplib2>=0.1.1",
        
        # AI/OpenAI
        "openai>=1.0.0",
        
        # GUI (optional)
        "PyQt6>=6.5.0",
        
        # Image processing (for thumbnails)
        "Pillow>=10.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "black>=23.7.0",
            "flake8>=6.1.0",
            "mypy>=1.5.0",
        ],
        "cuda": [
            "torch>=2.0.0+cu118",
            "torchaudio>=2.0.0+cu118",
        ],
    },
    entry_points={
        "console_scripts": [
            "sejm-highlights=app:main",
            "sejm-pipeline=pipeline.processor:main",
        ],
    },
    include_package_data=True,
    package_data={
        "pipeline": ["*.yml", "*.yaml", "models/*.csv"],
    },
    zip_safe=False,
)