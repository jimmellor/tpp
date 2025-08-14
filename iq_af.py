#!/usr/bin/env python

# Program iq_af.py - manage I/Q audio from soundcard using pyaudio
# Copyright (C) 2013-2014 Martin Ewing
# Enhanced with audio output functionality
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR ANY PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Contact the author by e-mail: aa6e@arrl.net
#
# Part of the iq.py program.
#

# HISTORY
# 01-04-2014 Initial release (QST article)
# 05-17-2014 timing improvements, esp for Raspberry Pi, etc.
#    implement 'skip'
# 2024 Enhanced with audio output functionality

import sys, time, threading
import queue
import pyaudio as pa
import numpy as np

# CALLBACK ROUTINE
# pyaudio callback routine is called when in_data buffer is ready.
# See pyaudio and portaudio documentation for details.
# Callback may not be called at a uniform rate.

# "skip = N" means "discard every (N+1)th buffer" (N > 0) or
#   "only use every (-N+1)th buffer" (N < 0)
# i.e. skip=2 -> discard every 3rd buffer; 
#       skip=-2 -> use every 3rd buffer.
# (skip=1 and skip=-1 have same effect!)
# skip=0 means take all data.

# Global variables (in this module's namespace!)
# globals are required to communicate with callback thread.
led_underrun_ct = 0             # buffer underrun LED 
cbcount = 0
MAXQUEUELEN = 32                # Don't use iq-opt for this?
cbqueue = queue.Queue(MAXQUEUELEN)  # will be queue to transmit af data
cbskip_ct = 0
queueLock = threading.Lock()    # protect queue accesses
cbfirst = 1                     # Skip this many buffers at start

def pa_callback_iqin(in_data, f_c, time_info, status):
    global cbcount, cbqueue, cbskip, cbskip_ct
    global led_underrun_ct, queueLock, cbfirst
    
    cbcount += 1

    if status == pa.paInputOverflow:
        led_underrun_ct = 1         # signal LED "underrun" (really, overflow)
    # Decide if we should skip this buffer or take it.
    # First, are we dropping every Nth buffer?
    if cbskip > 0:                  # Yes, we must check cbskip_ct
        if cbskip_ct >= cbskip:
            cbskip_ct = 0
            return (None, pa.paContinue)    # Discard this buffer
        else:
            cbskip_ct += 1                  # OK to process buffer
    # Or, are we accepting every Nth buffer?
    if cbskip < 0:
        if cbskip_ct >= -cbskip:
            cbskip_ct = 0                   # OK to process buffer
        else:
            cbskip_ct += 1
            return (None, pa.paContinue)    # Discard this buffer
    # Having decided to take the current buffer, or cbskip==0, 
    #    send it to main thread.
    if cbfirst > 0:
        cbfirst -= 1
        return (None, pa.paContinue)    # Toss out first N data
    try:
        queueLock.acquire()
        cbqueue.put_nowait(in_data)     # queue should sync with main thread
        queueLock.release()
    except queue.Full:
        print("ERROR: Internal queue is filled.  Reconfigure to use less CPU.")
        print("\n\n (Ignore remaining errors!)")
        sys.exit()
    return (None, pa.paContinue)    # Return to pyaudio.  All OK.
# END OF CALLBACK ROUTINE

class DataInput(object):
    """ Set up audio input with callbacks.
    """
    def __init__(self, opt=None):

        # Initialize pyaudio (A python mapping of PortAudio) 
        # Consult pyaudio documentation.
        self.audio = pa.PyAudio()   # generates lots of warnings.
        print()
        self.afiqstream = None      # Initialize input stream
        self.afoutstream = None     # Initialize output stream
        self.Restart(opt)
        return
        
    def Restart(self, opt):         # Maybe restart after error?
        global cbqueue, cbskip

        cbskip = opt.skip
        print()
        # set up stereo / 48K IQ input channel.  Stream will be started.
        if opt.index < 0:       # Find pyaudio's idea of default index
            defdevinfo = self.audio.get_default_input_device_info()
            print(("Default device index is %d; id='%s'"%(defdevinfo['index'], defdevinfo['name'])))
            af_using_index = defdevinfo['index']
        else:
            af_using_index = opt.index              # Use user's choice of index
            devinfo = self.audio.get_device_info_by_index(af_using_index)
            print(("Using device index %d; id='%s'" % (devinfo['index'], devinfo['name'])))
        
        # Find output device (use default for now)
        try:
            defoutdevinfo = self.audio.get_default_output_device_info()
            print(("Default output device index is %d; id='%s'"%(defoutdevinfo['index'], defoutdevinfo['name'])))
            af_out_index = defoutdevinfo['index']
        except:
            print("No default output device found, audio output disabled")
            af_out_index = None
            
        try:
            # Verify input mode is supported.
            support = self.audio.is_format_supported(
                    input_format=pa.paInt16,        # 16 bit samples
                    input_channels=2,               # 2 channels (stereo)
                    rate=opt.sample_rate,           # typ. 48000
                    input_device=af_using_index)
            print("Input audio mode is supported:", support)
            
            # Verify output mode is supported.
            if af_out_index is not None:
                support_out = self.audio.is_format_supported(
                        output_format=pa.paInt16,       # 16 bit samples
                        output_channels=2,              # 2 channels (stereo)
                        rate=opt.sample_rate,           # typ. 48000
                        output_device=af_out_index)
                print("Output audio mode is supported:", support_out)
                
        except ValueError as e:
            print(("ERROR self.audio.is_format_supported", e))
            #sys.exit()
            
        # Open input stream
        try:
            self.afiqstream = self.audio.open( 
                        format=pa.paInt16,          # 16 bit samples
                        channels=2,                 # 2 channels
                        rate=opt.sample_rate,       # typ. 48000
                        frames_per_buffer= opt.buffers * opt.size,
                        input_device_index=af_using_index,
                        input=True,                 # being used for input only
                        stream_callback=pa_callback_iqin )
            print("Audio input stream opened successfully")
        except Exception as e:
            print("Failed to open audio input stream:", e)
            self.afiqstream = None
            
        # Open output stream
        if af_out_index is not None:
            try:
                self.afoutstream = self.audio.open(
                            format=pa.paInt16,          # 16 bit samples
                            channels=2,                 # 2 channels
                            rate=opt.sample_rate,       # typ. 48000
                            frames_per_buffer=opt.size, # Smaller buffer for output
                            output_device_index=af_out_index,
                            output=True,                # being used for output only
                            stream_callback=None)       # No callback for output
                print("Audio output stream opened successfully")
            except Exception as e:
                print("Failed to open audio output stream:", e)
                self.afoutstream = None
        return

    def get_queued_data(self):
        timeout = 40
        while cbqueue.qsize() < 4:
            timeout -= 1
            if timeout <= 0: 
                print("timeout waiting for queue to become non-empty!")
                sys.exit()
            time.sleep(.1)
        queueLock.acquire()
        data = cbqueue.get(True, 4.)    # Why addnl timeout set?
        queueLock.release()
        return data

    def play_audio(self, audio_data):
        """Play audio data through the output stream"""
        if self.afoutstream and self.afoutstream.is_active():
            try:
                # Ensure data is in the right format (16-bit stereo)
                if isinstance(audio_data, np.ndarray):
                    # Convert to int16 if it's float
                    if audio_data.dtype != np.int16:
                        # Normalize and convert to int16
                        if audio_data.dtype == np.float32 or audio_data.dtype == np.float64:
                            # Normalize to [-1, 1] range and convert to int16
                            max_val = np.max(np.abs(audio_data))
                            if max_val > 0:
                                audio_data = (audio_data / max_val * 32767).astype(np.int16)
                            else:
                                audio_data = audio_data.astype(np.int16)
                        else:
                            audio_data = audio_data.astype(np.int16)
                    
                    # Ensure stereo (2 channels)
                    if len(audio_data.shape) == 1:
                        # Mono - duplicate to stereo
                        audio_data = np.column_stack((audio_data, audio_data))
                    elif audio_data.shape[1] == 1:
                        # Mono - duplicate to stereo
                        audio_data = np.column_stack((audio_data.flatten(), audio_data.flatten()))
                    
                    # Convert to bytes for PyAudio
                    audio_bytes = audio_data.tobytes()
                else:
                    # Assume it's already bytes
                    audio_bytes = audio_data
                
                # Write to output stream
                self.afoutstream.write(audio_bytes)
                return True
            except Exception as e:
                print("Error playing audio:", e)
                return False
        return False

    def play_demodulated_audio(self, iq_data, demod_type='am'):
        """Demodulate I/Q data and play the resulting audio"""
        if self.afoutstream and self.afoutstream.is_active():
            try:
                # Convert to complex if needed
                if isinstance(iq_data, np.ndarray):
                    if iq_data.dtype == np.int16:
                        # Convert from int16 to float
                        iq_data = iq_data.astype(np.float32) / 32767.0
                    
                    # Extract I and Q channels
                    if len(iq_data.shape) == 2 and iq_data.shape[1] == 2:
                        # Stereo data, extract I and Q
                        i_data = iq_data[:, 0]
                        q_data = iq_data[:, 1]
                    else:
                        # Assume interleaved I/Q
                        i_data = iq_data[::2]
                        q_data = iq_data[1::2]
                    
                    # Demodulate based on type
                    if demod_type.lower() == 'am':
                        # AM demodulation: sqrt(I^2 + Q^2)
                        audio = np.sqrt(i_data**2 + q_data**2)
                    elif demod_type.lower() == 'fm':
                        # FM demodulation: derivative of phase
                        phase = np.arctan2(q_data, i_data)
                        # Unwrap phase to avoid discontinuities
                        phase_unwrapped = np.unwrap(phase)
                        # Take derivative (difference)
                        audio = np.diff(phase_unwrapped)
                        # Pad to match original length
                        audio = np.concatenate(([audio[0]], audio))
                    else:
                        # Default to AM
                        audio = np.sqrt(i_data**2 + q_data**2)
                    
                    # Apply some filtering and normalization
                    # Simple low-pass filter to reduce noise
                    from scipy.signal import butter, filtfilt
                    try:
                        # Design low-pass filter
                        nyquist = self.afoutstream._rate / 2
                        cutoff = 3000  # 3 kHz cutoff
                        normal_cutoff = cutoff / nyquist
                        b, a = butter(4, normal_cutoff, btype='low', analog=False)
                        audio = filtfilt(b, a, audio)
                    except:
                        # If scipy not available, skip filtering
                        pass
                    
                    # Normalize and convert to int16
                    max_val = np.max(np.abs(audio))
                    if max_val > 0:
                        audio = (audio / max_val * 32767).astype(np.int16)
                    else:
                        audio = audio.astype(np.int16)
                    
                    # Convert to stereo
                    audio_stereo = np.column_stack((audio, audio))
                    
                    # Play the audio
                    return self.play_audio(audio_stereo)
                    
            except Exception as e:
                print("Error in demodulation:", e)
                return False
        return False

    def CPU_load(self):
        if self.afiqstream:
            load = self.afiqstream.get_cpu_load()
            return load
        return 0

    def isActive(self):
        if self.afiqstream:
            return self.afiqstream.is_active()
        return False
        
    def Start(self):                            # Start pyaudio stream 
        if self.afiqstream:
            self.afiqstream.start_stream()
        if self.afoutstream:
            self.afoutstream.start_stream()

    def Stop(self):                             # Stop pyaudio stream
        if self.afiqstream:
            self.afiqstream.stop_stream()
        if self.afoutstream:
            self.afoutstream.stop_stream()
    
    def CloseStream(self):
        if self.afiqstream:
            self.afiqstream.stop_stream()
            self.afiqstream.close()
        if self.afoutstream:
            self.afoutstream.stop_stream()
            self.afoutstream.close()

    def Terminate(self):                        # Stop and release all resources
        self.CloseStream()
        self.audio.terminate()

if __name__ == '__main__':
    print('debug')           # Insert module test code below

