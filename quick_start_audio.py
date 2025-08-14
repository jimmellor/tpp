#!/usr/bin/env python

# Quick Start Script for Audio Output
# This script provides easy access to the audio output functionality

import sys
import os
import subprocess

def check_dependencies():
    """Check if required dependencies are installed"""
    required_modules = ['numpy', 'pygame', 'pyaudio']
    missing_modules = []
    
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        print("Missing required modules:", ", ".join(missing_modules))
        print("Install them with: pip install -r requirements.txt")
        return False
    
    print("✓ All required dependencies are installed")
    return True

def show_audio_devices():
    """Show available audio devices"""
    print("\n=== Available Audio Devices ===")
    try:
        result = subprocess.run(['python', 'pa.py'], capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout)
        else:
            print("Could not run pa.py to show devices")
    except Exception as e:
        print(f"Error showing audio devices: {e}")

def run_with_audio_output(source_type="rtl", demod_type="am"):
    """Run the main program with audio output enabled"""
    cmd = [
        'python', 'iq.py',
        '--audio_out',
        '--demod', demod_type,
        '--WATERFALL'
    ]
    
    if source_type == "rtl":
        cmd.extend(['--RTL'])
        print(f"Starting RTL-SDR with {demod_type.upper()} demodulation and audio output...")
    else:
        cmd.extend(['--index', '0'])  # Use default audio input
        print(f"Starting audio input with {demod_type.upper()} demodulation and audio output...")
    
    print(f"Command: {' '.join(cmd)}")
    print("\nPress Ctrl+C to stop")
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Error running program: {e}")

def main():
    print("🎵 Tiny Python Panadapter - Audio Output Quick Start")
    print("=" * 55)
    
    # Check dependencies
    if not check_dependencies():
        return
    
    # Show audio devices
    show_audio_devices()
    
    print("\n=== Quick Start Options ===")
    print("1. RTL-SDR with AM demodulation and audio output")
    print("2. RTL-SDR with FM demodulation and audio output")
    print("3. Audio input with AM demodulation and audio output")
    print("4. Audio input with FM demodulation and audio output")
    print("5. Test audio output only")
    print("6. Show help and exit")
    
    while True:
        try:
            choice = input("\nEnter your choice (1-6): ").strip()
            
            if choice == "1":
                run_with_audio_output("rtl", "am")
                break
            elif choice == "2":
                run_with_audio_output("rtl", "fm")
                break
            elif choice == "3":
                run_with_audio_output("audio", "am")
                break
            elif choice == "4":
                run_with_audio_output("audio", "fm")
                break
            elif choice == "5":
                print("\nRunning audio output test...")
                subprocess.run(['python', 'test_audio_output.py'])
                break
            elif choice == "6":
                print("\n=== Help ===")
                print("• Make sure your speakers/headphones are connected")
                print("• Ensure system volume is up and not muted")
                print("• For RTL-SDR: Connect your dongle")
                print("• For audio input: Connect radio IF output to sound card")
                print("\nFull documentation: AUDIO_OUTPUT_README.md")
                break
            else:
                print("Invalid choice. Please enter 1-6.")
                
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
