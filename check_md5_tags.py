#!/usr/bin/env python3
"""
Simple script to check MD5 tags in audio files using mutagen.
"""

import os
import sys
from mutagen import File
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

def check_md5_tag(file_path):
    """Check for MD5 tag in audio file."""
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
    
    try:
        audio_file = File(file_path)
        if audio_file is None:
            print(f"Unsupported file format: {file_path}")
            return
        
        print(f"\nFile: {os.path.basename(file_path)}")
        print(f"Path: {file_path}")
        print(f"Type: {type(audio_file).__name__}")
        
        # Check for MD5 tag based on file type
        md5_found = False
        
        if isinstance(audio_file, FLAC):
            # Check for MD5 tag in metadata
            if 'MD5' in audio_file:
                print(f"MD5 Tag: {audio_file['MD5'][0]}")
                md5_found = True
            else:
                print("MD5 Tag: Not found")
            
            # Check for MD5 signature in STREAMINFO block (unencoded content)
            md5_signature = getattr(audio_file.info, 'md5_signature', 0)
            if md5_signature and md5_signature != 0:
                # Convert from int to hex string
                md5_hex = f"{md5_signature:032x}"
                print(f"MD5 of unencoded content: {md5_hex}")
                md5_found = True
            else:
                print("MD5 of unencoded content: 00000000000000000000000000000000 (unset)")
        
        elif isinstance(audio_file, MP3):
            if 'TXXX:MD5' in audio_file:
                print(f"MD5 Tag: {audio_file['TXXX:MD5'][0]}")
                md5_found = True
            else:
                print("MD5 Tag: Not found")
        
        elif isinstance(audio_file, MP4):
            if '----:com.apple.itunes:MD5' in audio_file:
                print(f"MD5 Tag: {audio_file['----:com.apple.itunes:MD5'][0].decode()}")
                md5_found = True
            else:
                print("MD5 Tag: Not found")
        
        else:
            # Try generic approach
            for key in audio_file.keys():
                if 'MD5' in str(key).upper():
                    print(f"MD5 Tag ({key}): {audio_file[key]}")
                    md5_found = True
                    break
            
            if not md5_found:
                print("MD5 Tag: Not found")
        
        # Show other interesting tags
        print("\nOther tags:")
        interesting_tags = ['title', 'artist', 'album', 'date', 'genre']
        for tag in interesting_tags:
            if tag in audio_file:
                print(f"  {tag.capitalize()}: {audio_file[tag][0] if isinstance(audio_file[tag], list) else audio_file[tag]}")
        
        return md5_found
        
    except Exception as e:
        print(f"Error reading file: {e}")

def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python check_md5_tags.py <audio_file> [audio_file2] ...")
        print("\nExample:")
        print("  python check_md5_tags.py downloads/Chronology\\ Vol.2\\ \\(40\\ -\\ 1985-2025\\)/01.\\ V.W.flac")
        return
    
    files_checked = 0
    files_with_md5 = 0
    
    for file_path in sys.argv[1:]:
        if os.path.isfile(file_path):
            if check_md5_tag(file_path):
                files_with_md5 += 1
            files_checked += 1
            print("-" * 60)
        elif os.path.isdir(file_path):
            # Check all audio files in directory
            audio_extensions = ['.flac', '.mp3', '.m4a', '.ogg', '.opus', '.wav']
            for root, dirs, files in os.walk(file_path):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in audio_extensions):
                        full_path = os.path.join(root, file)
                        if check_md5_tag(full_path):
                            files_with_md5 += 1
                        files_checked += 1
                        print("-" * 60)
        else:
            print(f"File or directory not found: {file_path}")
    
    print(f"\nSummary:")
    print(f"Files checked: {files_checked}")
    print(f"Files with MD5 tags: {files_with_md5}")
    print(f"Files without MD5 tags: {files_checked - files_with_md5}")

if __name__ == "__main__":
    main()
