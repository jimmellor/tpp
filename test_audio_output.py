#!/usr/bin/env python

# Test script for audio output functionality
# This script demonstrates how to use the enhanced audio output features

import numpy as np
import time
import sys
import os

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import iq_af as af
    import iq_opt as options
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running this from the same directory as the other .py files")
    sys.exit(1)

def test_audio_output():
    """Test the audio output functionality"""
    print("Testing Audio Output Functionality")
    print("=" * 40)
    
    # Create options with audio output enabled
    opt = options.opt
    opt.audio_output = True
    opt.demod_type = 'am'
    opt.sample_rate = 48000
    opt.size = 1024
    opt.buffers = 4
    
    print(f"Sample rate: {opt.sample_rate} Hz")
    print(f"FFT size: {opt.size}")
    print(f"Demodulation: {opt.demod_type.upper()}")
    print()
    
    try:
        # Initialize audio system
        print("Initializing audio system...")
        audio_system = af.DataInput(opt)
        
        # Start audio streams
        print("Starting audio streams...")
        audio_system.Start()
        
        print("Audio system initialized successfully!")
        print("You should now hear audio output from your speakers/headphones")
        print()
        print("Press Ctrl+C to stop...")
        
        # Generate test I/Q data (simulated radio signal)
        print("Generating test I/Q data...")
        
        # Create a simple AM signal: carrier + audio tone
        t = np.linspace(0, 1, opt.size * opt.buffers)
        carrier_freq = 1000  # 1 kHz carrier
        audio_freq = 440     # 440 Hz audio tone (A note)
        
        # AM modulation: (1 + m*cos(2π*fm*t)) * cos(2π*fc*t)
        modulation_index = 0.5
        carrier = np.cos(2 * np.pi * carrier_freq * t)
        audio = np.cos(2 * np.pi * audio_freq * t)
        am_signal = (1 + modulation_index * audio) * carrier
        
        # Convert to I/Q format (simplified - just use the AM signal for both I and Q)
        i_data = am_signal.astype(np.float32)
        q_data = np.zeros_like(i_data)  # No quadrature component for simple AM
        
        # Convert to int16 format
        i_data_int16 = (i_data * 32767).astype(np.int16)
        q_data_int16 = (q_data * 32767).astype(np.int16)
        
        # Combine into I/Q format
        iq_data = np.column_stack((i_data_int16, q_data_int16))
        
        print("Playing test audio...")
        
        # Play the audio for a few seconds
        start_time = time.time()
        while time.time() - start_time < 5:  # Play for 5 seconds
            # Play the demodulated audio
            audio_system.play_demodulated_audio(iq_data, opt.demod_type)
            time.sleep(0.1)  # Small delay between chunks
        
        print("Test completed!")
        
    except KeyboardInterrupt:
        print("\nStopping audio...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        try:
            if 'audio_system' in locals():
                print("Cleaning up...")
                audio_system.Stop()
                audio_system.Terminate()
        except:
            pass
        print("Audio system stopped.")

def test_different_demod_types():
    """Test different demodulation types"""
    print("\nTesting Different Demodulation Types")
    print("=" * 40)
    
    opt = options.opt
    opt.audio_output = True
    opt.sample_rate = 48000
    opt.size = 1024
    opt.buffers = 4
    
    demod_types = ['am', 'fm']
    
    for demod_type in demod_types:
        print(f"\nTesting {demod_type.upper()} demodulation...")
        opt.demod_type = demod_type
        
        try:
            audio_system = af.DataInput(opt)
            audio_system.Start()
            
            # Generate test signal
            t = np.linspace(0, 1, opt.size * opt.buffers)
            
            if demod_type == 'am':
                # AM signal
                carrier_freq = 1000
                audio_freq = 440
                carrier = np.cos(2 * np.pi * carrier_freq * t)
                audio = np.cos(2 * np.pi * audio_freq * t)
                signal = (1 + 0.5 * audio) * carrier
            else:  # FM
                # FM signal
                carrier_freq = 1000
                audio_freq = 440
                # Simple FM: frequency varies with audio
                freq_deviation = 100  # Hz
                phase = 2 * np.pi * carrier_freq * t + freq_deviation * np.sin(2 * np.pi * audio_freq * t) / audio_freq
                signal = np.cos(phase)
            
            # Convert to I/Q format
            i_data = (signal * 32767).astype(np.int16)
            q_data = np.zeros_like(i_data)
            iq_data = np.column_stack((i_data, q_data))
            
            print(f"Playing {demod_type.upper()} test signal for 3 seconds...")
            start_time = time.time()
            while time.time() - start_time < 3:
                audio_system.play_demodulated_audio(iq_data, demod_type)
                time.sleep(0.1)
            
            audio_system.Stop()
            audio_system.Terminate()
            
        except Exception as e:
            print(f"Error testing {demod_type}: {e}")

if __name__ == "__main__":
    print("Audio Output Test Script")
    print("This script tests the enhanced audio output functionality")
    print("Make sure your speakers/headphones are connected and volume is up")
    print()
    
    try:
        test_audio_output()
        test_different_demod_types()
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Test failed: {e}")
    
    print("\nTest completed!")
