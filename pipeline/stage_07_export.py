"""
Stage 7: Video Export & Assembly
- Extract individual clips z source video
- Generate title cards
- Add transitions (fade in/out)
- Concatenate wszystko
- Optional: hardsub version
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

from .config import Config
load_dotenv()

class ExportStage:
    def __init__(self, config: Config):
        self.config = config
        self._check_ffmpeg()
        
        # Initialize GPT
        self.openai_client = None
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                self.openai_client = OpenAI(api_key=api_key)
            except:
                pass
    
    def _generate_gpt_title(self, clips: List[Dict]) -> str:
        """Generuj clickbait z GPT-4o-mini"""
        
        if not self.openai_client:
            # Fallback bez GPT
            from datetime import datetime
            date = datetime.now().strftime("%d.%m.%Y")
            return f"NAJLEPSZE MOMENTY! 🔥 | Sejm Highlights {date}"
        
        # Przygotuj kontekst - top 3 klipy
        context = "Najciekawsze fragmenty debaty:\n\n"
        for i, clip in enumerate(clips[:3], 1):
            transcript = clip.get('transcript', '')[:300]
            score = clip.get('final_score', 0)
            context += f"Fragment {i} (score: {score:.2f}):\n{transcript}\n\n"
        
        from datetime import datetime
        date = datetime.now().strftime("%d.%m.%Y")
        
        prompt = f"""Jesteś ekspertem od tworzenia viralowych tytułów YouTube dla polskiej polityki.

    {context}

    Wygeneruj clickbaitowy tytuł wideo (max 80 znaków) który:
    - Jest emocjonalny i przyciąga uwagę
    - Używa CAPSLOCK dla kluczowych słów
    - Ma 1-2 emoji (🔥💥⚡😱🤯)
    - NIE używa liczb w stylu "TOP 5"
    - Jest w formacie: [GŁÓWNY CLICKBAIT] | Sejm Highlights {date}

    Przykłady dobrych tytułów:
    - "OSTRA WYMIANA o budżecie! 🔥 | Sejm Highlights {date}"
    - "Poseł PRZERWAŁ debatę! 💥 | Sejm Highlights {date}"
    - "SKANDAL w Sejmie! Kontrowersja ⚡ | Sejm Highlights {date}"

    Wygeneruj TYLKO tytuł, bez dodatkowych wyjaśnień."""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Jesteś ekspertem od viralowych tytułów politycznych."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.9
            )
            
            title = response.choices[0].message.content.strip()
            print(f"   🤖 GPT wygenerował tytuł: {title}")
            return title
            
        except Exception as e:
            print(f"   ⚠️ Błąd GPT API: {e}")
            return f"NAJLEPSZE MOMENTY! 🔥 | Sejm Highlights {date}"
    
    def _check_ffmpeg(self):
        """Sprawdź ffmpeg"""
        try:
            subprocess.run(
                ['ffmpeg', '-version'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("❌ ffmpeg nie jest zainstalowany!")
    
    def process(
        self,
        input_file: str,
        clips: List[Dict],
        segments: List[Dict],
        output_dir: Path,
        session_dir: Path,
        progress_callback: Optional[Callable] = None,
        part_number: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Główna metoda przetwarzania
        
        Args:
            part_number: Numer części (dla multi-part export) - None dla single export
        
        Returns:
            Dict zawierający output_file path
        """
        part_suffix = f"_part{part_number}" if part_number else ""
        print(f"🎬 Video export{f' (część {part_number})' if part_number else ''}: {len(clips)} klipów...")
        
        input_path = Path(input_file)
        
        # Create subdirs - osobne dla każdej części!
        clips_dir = session_dir / f"clips{part_suffix}"
        titles_dir = session_dir / f"titles{part_suffix}"
        clips_dir.mkdir(exist_ok=True)
        titles_dir.mkdir(exist_ok=True)
        
        # STEP 1: Extract individual clips
        if progress_callback:
            progress_callback(0.1, "Wycinanie klipów...")
        
        self._extract_clips(input_path, clips, clips_dir)
        
        # STEP 2: Generate title cards (if enabled)
        title_cards_generated = False
        if self.config.export.add_transitions:
            if progress_callback:
                progress_callback(0.3, "Generowanie title cards...")
            
            try:
                self._generate_title_cards(clips, titles_dir)
                title_cards_generated = True
            except Exception as e:
                print(f"   ⚠️ Błąd title cards (pomijam): {e}")
                # Continue without title cards
                for clip in clips:
                    clip['title_card_file'] = None
        
        # STEP 3: Add transitions (fade in/out)
        if progress_callback:
            progress_callback(0.5, "Dodawanie przejść...")
        
        faded_clips = self._add_transitions(clips, clips_dir)
        
        # STEP 4: Concatenate wszystko
        if progress_callback:
            progress_callback(0.7, "Łączenie klipów...")
        
        output_file = self._concatenate_clips(
            clips,
            faded_clips,
            titles_dir,
            output_dir,
            input_path,
            title_cards_generated,
            part_number=part_number  # ✅ Przekazanie part_number
        )
        
        # STEP 5: Generate hardsub version (optional)
        output_file_hardsub = None
        if self.config.export.generate_hardsub:
            if progress_callback:
                progress_callback(0.9, "Generowanie wersji z napisami...")
            
            try:
                output_file_hardsub = self._generate_hardsub(
                    output_file,
                    clips,
                    segments,
                    output_dir
                )
            except Exception as e:
                print(f"   ⚠️ Błąd hardsub: {e}")
        
        print("✅ Stage 7 zakończony")
        
        return {
            'output_file': str(output_file),
            'output_file_hardsub': str(output_file_hardsub) if output_file_hardsub else None,
            'num_clips': len(clips)
        }
    
    def _extract_clips(
        self,
        input_file: Path,
        clips: List[Dict],
        output_dir: Path
    ):
        """Extract individual clips from source video"""
        print(f"   Wycinanie {len(clips)} klipów...")
        
        for i, clip in enumerate(clips):
            # Pre/post roll
            t0 = max(0, clip['t0'] - self.config.export.clip_preroll)
            t1 = clip['t1'] + self.config.export.clip_postroll
            
            output_file = output_dir / f"clip_{i+1:03d}.mp4"
            
            # ffmpeg precise cut (re-encode needed for B-frames)
            cmd = [
                'ffmpeg',
                '-hwaccel', 'cuda',  # GPU hardware decoding
                '-ss', str(t0),
                '-to', str(t1),
                '-i', str(input_file),
                '-c:v', self.config.export.video_codec,
                '-preset', self.config.export.video_preset,
                '-crf', str(self.config.export.crf),
                '-c:a', self.config.export.audio_codec,
                '-b:a', self.config.export.audio_bitrate,
                '-movflags', self.config.export.movflags,
                '-y',
                str(output_file)
            ]
            
            try:
                subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True
                )
                
                clip['clip_file'] = str(output_file)
                
            except subprocess.CalledProcessError as e:
                print(f"   ⚠️ Błąd wycinania klipu {i+1}: {e.stderr.decode()}")
                raise
        
        print(f"   ✓ Wycięto {len(clips)} klipów")
    
    def _generate_title_cards(
        self,
        clips: List[Dict],
        output_dir: Path
    ):
        """Generate title cards for each clip"""
        print(f"   Generowanie {len(clips)} title cards...")
        
        duration = self.config.export.title_card_duration
        fontsize = self.config.export.title_fontsize
        fontcolor = self.config.export.title_fontcolor
        bgcolor = self.config.export.title_bgcolor
        
        for i, clip in enumerate(clips):
            title = clip.get('title', 'Ciekawy moment')
            output_file = output_dir / f"title_{i+1:03d}.mp4"
            
            # Escape title for ffmpeg (simple approach - remove special chars)
            title_safe = title.replace("'", "").replace('"', "").replace(":", " -")
            
            # Generate black background with text using drawtext filter
            cmd = [
                'ffmpeg',
                '-f', 'lavfi',
                '-i', f'color=c={bgcolor}:s=1920x1080:d={duration}',
                '-vf', f"drawtext=text='{title_safe}':fontsize={fontsize}:fontcolor={fontcolor}:x=(w-text_w)/2:y=(h-text_h)/2",
                '-c:v', self.config.export.video_codec,
                '-preset', self.config.export.video_preset,  # Use GPU preset (p5 for NVENC)
                '-crf', str(self.config.export.crf),
                '-pix_fmt', 'yuv420p',
                '-y',
                str(output_file)
            ]
            
            try:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True
                )
                
                clip['title_card_file'] = str(output_file)
                
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.decode() if e.stderr else str(e)
                if 'Fontconfig error' in error_msg or 'Cannot load default config' in error_msg:
                    print(f"   ⚠️ Błąd fontconfig dla title card {i+1} - pomijam title cards")
                    raise RuntimeError("Fontconfig not available")
                else:
                    print(f"   ⚠️ Błąd title card {i+1}: {error_msg[:200]}")
                    clip['title_card_file'] = None
        
        print(f"   ✓ Wygenerowano title cards")
    
    def _add_transitions(
        self,
        clips: List[Dict],
        clips_dir: Path
    ) -> List[str]:
        """Add fade in/out transitions to clips"""
        print(f"   Dodawanie przejść do {len(clips)} klipów...")
        
        fade_in = self.config.export.fade_in_duration
        fade_out = self.config.export.fade_out_duration
        
        faded_files = []
        
        for i, clip in enumerate(clips):
            if 'clip_file' not in clip:
                continue
            
            input_file = Path(clip['clip_file'])
            output_file = clips_dir / f"clip_{i+1:03d}_faded.mp4"
            
            # Get clip duration for fade out timing
            duration = clip['duration'] + self.config.export.clip_preroll + self.config.export.clip_postroll
            fade_out_start = max(0, duration - fade_out)
            
            # Fade video and audio
            cmd = [
                'ffmpeg',
                '-i', str(input_file),
                '-vf', f"fade=t=in:st=0:d={fade_in},fade=t=out:st={fade_out_start}:d={fade_out}",
                '-af', f"afade=t=in:st=0:d={fade_in},afade=t=out:st={fade_out_start}:d={fade_out}",
                '-c:v', self.config.export.video_codec,
                '-preset', self.config.export.video_preset,  # Use GPU preset (p5 for NVENC)
                '-crf', str(self.config.export.crf),
                '-c:a', self.config.export.audio_codec,
                '-b:a', self.config.export.audio_bitrate,
                '-y',
                str(output_file)
            ]
            
            try:
                subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True
                )
                
                faded_files.append(str(output_file))
                
            except subprocess.CalledProcessError as e:
                print(f"   ⚠️ Błąd fade dla klipu {i+1}, używam original")
                faded_files.append(clip['clip_file'])
        
        print(f"   ✓ Dodano przejścia")
        return faded_files
    
    def _concatenate_clips(
        self,
        clips: List[Dict],
        faded_clips: List[str],
        titles_dir: Path,
        output_dir: Path,
        input_file: Path,
        has_title_cards: bool,
        part_number: Optional[int] = None
    ) -> Path:
        """Concatenate all clips into final video"""
        print(f"   Łączenie {len(clips)} klipów...")
        
        # Build concat list with ABSOLUTE paths
        concat_list = []
        
        for i, clip in enumerate(clips):
            # Add title card if exists
            if has_title_cards and self.config.export.add_transitions and clip.get('title_card_file'):
                title_path = Path(clip['title_card_file']).absolute()
                # Use forward slashes and escape for Windows
                concat_list.append(f"file '{str(title_path).replace(chr(92), '/')}'")
            
            # Add faded clip
            if i < len(faded_clips):
                clip_path = Path(faded_clips[i]).absolute()
                # Use forward slashes and escape for Windows
                concat_list.append(f"file '{str(clip_path).replace(chr(92), '/')}'")
        
        # Save concat list - osobny dla każdej części
        part_suffix_file = f"_part{part_number}" if part_number else ""
        concat_file = titles_dir.parent / f"concat_list{part_suffix_file}.txt"
        with open(concat_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(concat_list))
        
        print(f"   Concat list zapisany: {concat_file}")
        print(f"   Zawartość ({len(concat_list)} wpisów):")
        for line in concat_list[:3]:
            print(f"      {line}")
        if len(concat_list) > 3:
            print(f"      ... ({len(concat_list) - 3} więcej)")
        
        # Generate output filename with part number if multi-part
        date_str = datetime.now().strftime("%Y-%m-%d")
        source_name = input_file.stem
        part_suffix = f"_PART{part_number}" if part_number else ""
        output_file = output_dir / f"SEJM_HIGHLIGHTS_{source_name}_{date_str}{part_suffix}.mp4"
        
        # Concatenate
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file.absolute()),
            '-c:v', self.config.export.video_codec,
            '-preset', self.config.export.video_preset,
            '-crf', str(self.config.export.crf),
            '-c:a', self.config.export.audio_codec,
            '-b:a', self.config.export.audio_bitrate,
            '-movflags', self.config.export.movflags,
            '-y',
            str(output_file.absolute())
        ]
        
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
            
            print(f"   ✓ Film zapisany: {output_file.name}")
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            print(f"   ❌ Błąd concatenation: {error_msg}")
            
            # Debug info
            print(f"\n   DEBUG INFO:")
            print(f"   Concat file exists: {concat_file.exists()}")
            print(f"   Concat file path: {concat_file.absolute()}")
            
            if concat_file.exists():
                with open(concat_file, 'r') as f:
                    content = f.read()
                    print(f"   Concat file content:\n{content[:500]}")
            
            # Check if files exist
            print(f"\n   Checking clip files:")
            for i, faded_clip in enumerate(faded_clips[:3]):
                exists = Path(faded_clip).exists()
                print(f"      Clip {i+1}: {exists} - {faded_clip}")
            
            raise
        
        return output_file
    
    def _generate_hardsub(
        self,
        input_file: Path,
        clips: List[Dict],
        segments: List[Dict],
        output_dir: Path
    ) -> Path:
        """Generate version with burned-in subtitles"""
        print(f"   Generowanie wersji z hardsub...")
        
        # Build SRT from clips
        srt_file = input_file.parent / "full_subtitles.srt"
        self._build_srt(clips, segments, srt_file)
        
        print(f"   SRT utworzony: {srt_file}")
        
        # Output file
        output_file = output_dir / input_file.name.replace('.mp4', '_HARDSUB.mp4')
        
        # Burn subtitles using subtitles filter
        # Convert Windows path to escaped format for ffmpeg
        srt_path_escaped = str(srt_file.absolute()).replace('\\', '/').replace(':', '\\:')
        
        fontsize = self.config.export.subtitle_fontsize
        
        # Use subtitles filter with proper escaping
        cmd = [
            'ffmpeg',
            '-hwaccel', 'cuda',  # GPU hardware decoding
            '-i', str(input_file.absolute()),
            '-vf', f"subtitles='{srt_path_escaped}':force_style='Fontsize={fontsize},Bold=1,Outline=2,Shadow=1,MarginV=40'",
            '-c:v', self.config.export.video_codec,
            '-preset', self.config.export.video_preset,  # Use GPU preset (p5 for NVENC)
            '-crf', str(self.config.export.crf),
            '-c:a', 'copy',
            '-y',
            str(output_file.absolute())
        ]
        
        print(f"   Uruchamiam ffmpeg dla hardsub...")
        
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                encoding='utf-8',
                errors='replace'
            )
            
            print(f"   ✓ Hardsub zapisany: {output_file.name}")
            return output_file
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            print(f"   ❌ Błąd hardsub: {error_msg[:500]}")
            
            # Try alternative method without subtitles filter
            print(f"   Próbuję alternatywnej metody (drawtext)...")
            return self._generate_hardsub_alternative(input_file, clips, output_dir, srt_file)
    
    def _build_srt(
        self,
        clips: List[Dict],
        segments: List[Dict],
        output_file: Path
    ):
        """Build SRT - FIXED: Account for ALL timing offsets + 0.5s early"""
        seg_lookup = {seg['id']: seg for seg in segments}
        
        # Napisy pojawiają się 0.5s wcześniej
        SUBTITLE_OFFSET = -0.5
        
        srt_lines = []
        subtitle_idx = 1
        cumulative_time = 0.0
        
        for clip_idx, clip in enumerate(clips):
            preroll = self.config.export.clip_preroll
            fade_in = self.config.export.fade_in_duration
            content_start = cumulative_time + preroll + fade_in
            
            seg_id = clip['id']
            segment = seg_lookup.get(seg_id)
            
            if not segment or 'words' not in segment or not segment['words']:
                transcript = clip.get('transcript', segment.get('transcript', '')) if segment else ''
                if transcript:
                    chunks = self._split_text_into_chunks(transcript, max_chars=60)
                    chunk_duration = clip['duration'] / len(chunks) if chunks else clip['duration']
                    
                    for i, chunk in enumerate(chunks):
                        chunk_start = content_start + (i * chunk_duration) + SUBTITLE_OFFSET
                        chunk_end = content_start + ((i + 1) * chunk_duration) + SUBTITLE_OFFSET
                        
                        # Ensure non-negative
                        chunk_start = max(0, chunk_start)
                        chunk_end = max(0, chunk_end)
                        
                        srt_lines.append(f"{subtitle_idx}")
                        srt_lines.append(f"{self._format_srt_time(chunk_start)} --> {self._format_srt_time(chunk_end)}")
                        srt_lines.append(chunk)
                        srt_lines.append("")
                        subtitle_idx += 1
                
                cumulative_time += (
                    preroll + fade_in + clip['duration'] + 
                    self.config.export.clip_postroll + self.config.export.fade_out_duration
                )
                continue
            
            words = segment['words']
            phrase_words = []
            phrase_start = None
            
            for i, word_info in enumerate(words):
                word_offset = word_info['start'] - clip['t0']
                word_end_offset = word_info['end'] - clip['t0']
                
                if word_offset < 0 or word_offset > clip['duration']:
                    continue
                
                word_start = content_start + word_offset + SUBTITLE_OFFSET
                word_end = content_start + word_end_offset + SUBTITLE_OFFSET
                
                # Ensure non-negative
                word_start = max(0, word_start)
                word_end = max(0, word_end)
                
                if phrase_start is None:
                    phrase_start = word_start
                
                phrase_words.append({
                    'word': word_info['word'],
                    'end': word_end
                })
                
                phrase_duration = word_end - phrase_start
                is_last_word = (i == len(words) - 1)
                
                should_end_phrase = (
                    len(phrase_words) >= 8 or
                    (len(phrase_words) >= 5 and phrase_duration >= 2.0) or
                    phrase_duration >= 3.5 or
                    is_last_word
                )
                
                if should_end_phrase and phrase_words:
                    phrase_text = ' '.join(w['word'] for w in phrase_words)
                    phrase_end = phrase_words[-1]['end']
                    
                    srt_lines.append(f"{subtitle_idx}")
                    srt_lines.append(f"{self._format_srt_time(phrase_start)} --> {self._format_srt_time(phrase_end)}")
                    srt_lines.append(phrase_text)
                    srt_lines.append("")
                    subtitle_idx += 1
                    
                    phrase_words = []
                    phrase_start = None
            
            cumulative_time += (
                preroll + fade_in + clip['duration'] + 
                self.config.export.clip_postroll + self.config.export.fade_out_duration
            )
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(srt_lines))
        
        print(f"   Total subtitle duration: {cumulative_time:.1f}s")
    
    @staticmethod
    def _split_text_into_chunks(text: str, max_chars: int = 60) -> List[str]:
        """Split text into subtitle-sized chunks"""
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0
        
        for word in words:
            word_length = len(word) + 1  # +1 for space
            
            if current_length + word_length > max_chars and current_chunk:
                # Finish current chunk
                chunks.append(' '.join(current_chunk))
                current_chunk = [word]
                current_length = word_length
            else:
                current_chunk.append(word)
                current_length += word_length
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks if chunks else [text]
    
    def _generate_hardsub_alternative(
        self,
        input_file: Path,
        clips: List[Dict],
        output_dir: Path,
        srt_file: Path
    ) -> Path:
        """Alternative hardsub method using ass filter"""
        print(f"   Metoda alternatywna: konwersja SRT -> ASS...")
        
        # Convert SRT to ASS (Advanced SubStation Alpha)
        ass_file = srt_file.parent / "full_subtitles.ass"
        
        # Simple SRT to ASS conversion
        self._convert_srt_to_ass(srt_file, ass_file)
        
        output_file = output_dir / input_file.name.replace('.mp4', '_HARDSUB.mp4')
        
        # Use ass filter (more reliable than subtitles filter on Windows)
        ass_path_escaped = str(ass_file.absolute()).replace('\\', '\\\\').replace(':', '\\:')

        cmd = [
            'ffmpeg',
            '-hwaccel', 'cuda',  # GPU hardware decoding
            '-i', str(input_file.absolute()),
            '-vf', f"ass='{ass_path_escaped}'",
            '-c:v', self.config.export.video_codec,
            '-preset', self.config.export.video_preset,  # Use GPU preset (p5 for NVENC)
            '-crf', str(self.config.export.crf),
            '-c:a', 'copy',
            '-y',
            str(output_file.absolute())
        ]
        
        try:
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
            
            print(f"   ✓ Hardsub (ASS) zapisany: {output_file.name}")
            return output_file
            
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Również nie udało się z ASS: {str(e)[:200]}")
            return None
    
    def _convert_srt_to_ass(self, srt_file: Path, ass_file: Path):
        """Convert SRT to ASS format"""
        # Read SRT
        with open(srt_file, 'r', encoding='utf-8') as f:
            srt_content = f.read()
        
        # ASS header
        fontsize = self.config.export.subtitle_fontsize
        ass_content = f"""[Script Info]
Title: Sejm Highlights Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{fontsize},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        # Parse SRT and convert to ASS
        # Simple regex-based parsing
        import re
        
        # Match SRT entries: number, timestamp, text
        pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n((?:.*\n?)+?)(?=\n\d+\n|\Z)'
        
        for match in re.finditer(pattern, srt_content):
            start = match.group(2).replace(',', '.')
            end = match.group(3).replace(',', '.')
            text = match.group(4).strip().replace('\n', '\\N')
            
            ass_content += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n"
        
        # Write ASS
        with open(ass_file, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        
        print(f"   SRT -> ASS konwersja zakończona")
    
    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """Format seconds to SRT time format (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    def cancel(self):
        """Anuluj operację"""
        pass


if __name__ == "__main__":
    # Test
    from .config import Config
    import json as js
    
    config = Config.load_default()
    stage = ExportStage(config)
    
    print("✅ ExportStage initialized successfully")
    print("⚠️ Full test requires actual video file and clips data")