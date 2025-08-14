#!/usr/bin/env python

# Program iq.py - spectrum displays from quadrature sampled IF data.
# Copyright (C) 2013-2014 Martin Ewing
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Contact the author by e-mail: aa6e@arrl.net
#
# Our goal is to display a zero-centered spectrum and waterfall on small
# computers, such as the BeagleBone Black or the Raspberry Pi, 
# spanning up to +/- 48 kHz (96 kHz sampling) with input from audio card
# or +/- 1.024 MHz from RTL dongle. 
#
# We use pyaudio, pygame, and pyrtlsdr Python libraries, which depend on
# underlying C/C++ libraries PortAudio, SDL, and rtl-sdr.
#

# HISTORY
# 01-04-2014 Initial release (QST article 4/2014)
# 05-17-2014 Improvements for RPi timing, etc.
#            Add REV, skip, sp_max/min, v_max/min options
# 05-31-2014 Add Si570 freq control option (DDS chip provided in SoftRock, eg.)
#           Note: Use of Si570 requires libusb-1.0 wrapper from 
#           https://pypi.python.org/pypi/libusb1/1.2.0
# 2024-XX-XX Added touchscreen frequency control support

# Note for directfb use (i.e. without X11/Xorg):
# User must be a member of the following Linux groups:
#   adm dialout audio video input (plus user's own group, e.g., pi)

import sys,time, threading, os, subprocess
import pygame as pg
import numpy  as np
import iq_dsp as dsp
import iq_wf  as wf
import iq_opt as options

# Some colors in PyGame style
BLACK =    (  0,   0,   0)
WHITE =    (255, 255, 255)
GREEN =    (  0, 255,   0)
NOTSOGREEN = (  0, 50,   0)
BLUE =     (  0,   0, 255)
RED =      (255,   0,   0)
YELLOW =   (192, 192,   0)
DARK_RED = (128,   0,   0)
LITE_RED = (255, 100, 100)
BGCOLOR =  (255, 230, 200)
BLUE_GRAY= (100, 100, 180)
ORANGE =   (255, 150,   0)
GRAY =     (192, 192, 192)
# RGBA colors - with alpha
TRANS_YELLOW = (255,255,0,150)

# Adjust for best graticule color depending on display gamma, resolution, etc.
GRAT_COLOR = NOTSOGREEN       # Color of graticule (grid)
GRAT_COLOR_2 = WHITE        # Color of graticule text
TRANS_OVERLAY = TRANS_YELLOW    # for info overlay
TCOLOR2 = ORANGE              # text color on info screen

INFO_CYCLE = 8      # Display frames per help info update

opt = options.opt   # Get option object from options module

# Touchscreen frequency control variables
touch_active = False
touch_start_x = 0
touch_start_y = 0
touch_start_freq = 0
touch_freq_step = opt.touch_sensitivity  # Frequency change per pixel movement
touch_freq_step_coarse = opt.touch_coarse_sensitivity  # kHz per pixel for coarse control
touch_feedback_msg = ""
touch_feedback_timer = 0
touch_feedback_alpha = 255  # Alpha value for fade-out effect
touch_gesture_start = False
touch_gesture_distance = 0
touch_last_tap_time = 0
touch_tap_count = 0
touch_start_time = 0
touch_long_press_threshold = 1.0  # seconds for long press

# print list of parameters to console.
print("identification:", opt.ident)
print("source        :", opt.source)
print("freq control  :", opt.control)
print("waterfall     :", opt.waterfall)
print("rev i/q       :", opt.rev_iq)
print("sample rate   :", opt.sample_rate)
print("size          :", opt.size)
print("buffers       :", opt.buffers)
print("skipping      :", opt.skip)
print("hamlib        :", opt.hamlib)
print("hamlib rigtype:", opt.hamlib_rigtype)
print("hamlib device :", opt.hamlib_device)
if opt.source=="rtl":
    print("rtl frequency :", opt.rtl_frequency)
    print("rtl gain      :", opt.rtl_gain)
if opt.control=="si570":
    print("si570 frequency :", opt.si570_frequency)
print("pulse         :", opt.pulse)
print("fullscreen    :", opt.fullscreen)
print("hamlib intvl  :", opt.hamlib_interval)
print("cpu load intvl:", opt.cpu_load_interval)
print("wf accum.     :", opt.waterfall_accumulation)
print("wf palette    :", opt.waterfall_palette)
print("sp_min, max   :", opt.sp_min, opt.sp_max)
print("v_min, max    :", opt.v_min, opt.v_max)
#print "max queue dept:", opt.max_queue
print("PCM290x lagfix:", opt.lagfix)
if opt.lcd4:
    print("LCD4 brightnes:", opt.lcd4_brightness)
print("Touchscreen   : Enabled for frequency control")
print("touch_sensitivity:", opt.touch_sensitivity)
print("touch_coarse_sensitivity:", opt.touch_coarse_sensitivity)

def quit_all():
    """ Quit pygames and close std outputs somewhat gracefully.
        Minimize console error messages.
    """
    pg.quit()
    try:
        sys.stdout.close()
    except:
        pass
    try:
        sys.stderr.close()
    except:
        pass
    sys.exit()

def handle_touch_frequency_change(dx, dy, control_type):
    """Handle touch-based frequency changes
    Args:
        dx: horizontal movement in pixels
        dy: vertical movement in pixels  
        control_type: type of frequency control (rtl, si570, hamlib)
    """
    global touch_freq_step, touch_freq_step_coarse, touch_feedback_msg, touch_feedback_timer, rigfreq_request, dataIn, mysi570, rigfreq
    
    # Use VERTICAL movement for frequency changes (landscape orientation)
    if abs(dy) > abs(dx):  # Vertical movement dominates
        freq_change = -dy * touch_freq_step  # Negative because Y increases downward
        if abs(dy) > 20:  # Coarse adjustment for larger movements
            freq_change = -dy * touch_freq_step_coarse
        
        print(f"Frequency change: {freq_change:.1f} kHz, control_type: {control_type}")
            
        if control_type == 'rtl':
            # RTL frequency control
            current_freq = dataIn.rtl.get_center_freq()
            new_freq = current_freq + freq_change * 1000  # Convert kHz to Hz
            dataIn.rtl.center_freq = new_freq
            touch_feedback_msg = f"RTL: {freq_change:+.1f} kHz"
            touch_feedback_timer = 30  # Show feedback for 30 frames
            print(f"RTL frequency changed by {freq_change:.1f} kHz to {new_freq/1e6:.3f} MHz")
            
        elif control_type == 'si570':
            # Si570 frequency control
            current_freq = mysi570.getFreqByValue() * 1000  # Convert to kHz
            new_freq = current_freq + freq_change
            mysi570.setFreqByValue(new_freq / 1000.0)  # Convert back to MHz
            touch_feedback_msg = f"Si570: {freq_change:.1f} kHz"
            touch_feedback_timer = 30  # Show feedback for 30 frames
            print(f"Si570 frequency changed by {freq_change:.1f} kHz to {new_freq:.3f} kHz")
            
        elif control_type == 'hamlib':
            # Hamlib frequency control
            if 'hamlib_available' in globals() and hamlib_available:
                new_freq = rigfreq + freq_change
                rigfreq_request = new_freq
                touch_feedback_msg = f"Hamlib: {freq_change:+.1f} kHz"
                touch_feedback_timer = 30  # Show feedback for 30 frames
                print(f"Hamlib frequency changed by {freq_change:.1f} kHz to {new_freq:.3f} kHz")
            else:
                touch_feedback_msg = "Hamlib not available"
                touch_feedback_timer = 30
                print("Hamlib not available for frequency control")

def handle_touch_parameter_change(dx, dy):
    """Handle touch-based parameter changes for non-frequency controls
    Args:
        dx: horizontal movement in pixels
        dy: vertical movement in pixels
    """
    global sp_min, sp_max, v_min, v_max, touch_feedback_msg, touch_feedback_timer, mygraticule, mywf, surf_2d_graticule
    
    # HORIZONTAL movement for dB scale adjustments (landscape orientation)
    if abs(dx) > 5:
        # Adjust spectrum dB limits
        if dx > 0:  # Moving right - increase upper limit
            if sp_max < 0:
                sp_max += 5
                mygraticule.set_range(sp_min, sp_max)
                surf_2d_graticule = mygraticule.make()
                touch_feedback_msg = f"Upper dB: {sp_max} dB"
                touch_feedback_timer = 30
        else:  # Moving left - decrease upper limit
            if sp_max > -130 and sp_max > sp_min + 10:
                sp_max -= 5
                mygraticule.set_range(sp_min, sp_max)
                surf_2d_graticule = mygraticule.make()
                touch_feedback_msg = f"Upper dB: {sp_max} dB"
                touch_feedback_timer = 30
        
        # Also adjust lower dB limit with vertical movement
        if abs(dy) > 5:
            if dy > 0:  # Moving down - increase lower limit
                if sp_min < sp_max - 10:
                    sp_min += 5
                    mygraticule.set_range(sp_min, sp_max)
                    surf_2d_graticule = mygraticule.make()
                    touch_feedback_msg = f"Lower dB: {sp_min} dB"
                    touch_feedback_timer = 30
            else:  # Moving up - decrease lower limit
                if sp_min > -140:
                    sp_min -= 5
                    mygraticule.set_range(sp_min, sp_max)
                    surf_2d_graticule = mygraticule.make()
                    touch_feedback_msg = f"Lower dB: {sp_min} dB"
                    touch_feedback_timer = 30
        
        # Adjust waterfall palette if enabled
        if opt.waterfall:
            if dx > 0:  # Moving right - increase upper threshold
                if v_max < -10:
                    v_max += 5
                    mywf.set_range(v_min, v_max)
                    touch_feedback_msg = f"WF upper: {v_max} dB"
                    touch_feedback_timer = 30
            else:  # Moving left - decrease upper threshold
                if v_max > v_min + 20:
                    v_max -= 5
                    mywf.set_range(v_min, v_max)
                    touch_feedback_msg = f"WF upper: {v_max} dB"
                    touch_feedback_timer = 30
            
            # Also adjust lower threshold with vertical movement
            if abs(dy) > 5:
                if dy > 0:  # Moving down - increase lower threshold
                    if v_min < v_max - 20:
                        v_min += 5
                        mywf.set_range(v_min, v_max)
                        touch_feedback_msg = f"WF lower: {v_min} dB"
                        touch_feedback_timer = 30
                else:  # Moving up - decrease lower threshold
                    if v_min > -130:
                        v_min -= 5
                        mywf.set_range(v_min, v_max)
                        touch_feedback_msg = f"WF lower: {v_min} dB"
                        touch_feedback_timer = 30

def handle_touch_gesture(touch1_pos, touch2_pos):
    """Handle multi-touch gestures for advanced controls
    Args:
        touch1_pos: position of first touch (x, y)
        touch2_pos: position of second touch (x, y)
    """
    global touch_feedback_msg, touch_feedback_timer, touch_freq_step
    
    # Calculate distance between touches for pinch gestures
    dx = touch2_pos[0] - touch1_pos[0]
    dy = touch2_pos[1] - touch1_pos[1]
    distance = (dx*dx + dy*dy)**0.5
    
    # Pinch to zoom - adjust frequency step size
    if distance < 100:  # Close touches - fine control
        touch_freq_step = opt.touch_sensitivity
        touch_feedback_msg = "Fine control mode"
        touch_feedback_timer = 30
    elif distance > 200:  # Far touches - coarse control
        touch_freq_step = opt.touch_coarse_sensitivity
        touch_feedback_msg = "Coarse control mode"
        touch_feedback_timer = 30

def handle_swipe_gesture(start_x, start_y, end_x, end_y, duration):
    """Handle swipe gestures for quick frequency changes
    Args:
        start_x: starting x position
        start_y: starting y position
        end_x: ending x position
        end_y: ending y position
        duration: duration of the swipe
    """
    global touch_feedback_msg, touch_feedback_timer, rigfreq_request, dataIn, mysi570, rigfreq
    
    if duration < 0.5:  # Quick swipe
        dx = end_x - start_x
        dy = end_y - start_y
        
        # Horizontal swipe for frequency changes
        if abs(dx) > abs(dy) and abs(dx) > 50:
            freq_change = dx * touch_freq_step * 2  # Faster change for swipes
            
            if opt.control == 'rtl':
                current_freq = dataIn.rtl.get_center_freq()
                new_freq = current_freq + freq_change * 1000
                dataIn.rtl.center_freq = new_freq
                touch_feedback_msg = f"Swipe: {freq_change:+.1f} kHz"
            elif opt.control == 'si570':
                current_freq = mysi570.getFreqByValue() * 1000
                new_freq = current_freq + freq_change
                mysi570.setFreqByValue(new_freq / 1000.0)
                touch_feedback_msg = f"Swipe: {freq_change:+.1f} kHz"
            elif opt.hamlib:
                new_freq = rigfreq + freq_change
                rigfreq_request = new_freq
                touch_feedback_msg = f"Swipe: {freq_change:+.1f} kHz"
            
            touch_feedback_timer = 60

def handle_touch_menu_navigation(x, y):
    """Handle touch-based menu navigation
    Args:
        x: x position of touch
        y: y position of touch
    """
    global info_phase, touch_feedback_msg, touch_feedback_timer
    
    # Define menu zones based on screen position
    if x < w_main / 3:  # Left third - previous menu
        if info_phase > 0:
            info_phase = (info_phase - 1) % 4
            touch_feedback_msg = f"Menu {info_phase}"
            touch_feedback_timer = 30
    elif x > 2 * w_main / 3:  # Right third - next menu
        if info_phase < 3:
            info_phase = (info_phase + 1) % 4
            touch_feedback_msg = f"Menu {info_phase}"
            touch_feedback_timer = 30
    else:  # Middle third - toggle menu on/off
        if info_phase > 0:
            info_phase = 0
            touch_feedback_msg = "Menu off"
        else:
            info_phase = 1
            touch_feedback_msg = "Menu on"
        touch_feedback_timer = 30

def handle_touch_quick_settings(x, y):
    """Handle touch-based quick settings
    Args:
        x: x position of touch
        y: y position of touch
    """
    global touch_feedback_msg, touch_feedback_timer, sp_min, sp_max, sp_min_def, sp_max_def, mygraticule, surf_2d_graticule, mywf, v_min, v_max, h_2d, w_main
    
    # Define quick settings zones based on screen position
    if y > 2 * h_2d / 3:  # Bottom third - quick settings
        if x < w_main / 4:  # Left quarter - toggle waterfall
            if opt.waterfall:
                opt.waterfall = False
                touch_feedback_msg = "Waterfall off"
            else:
                opt.waterfall = True
                touch_feedback_msg = "Waterfall on"
            touch_feedback_timer = 60
        elif x < 2 * w_main / 4:  # Left middle quarter - toggle fullscreen
            if opt.fullscreen:
                opt.fullscreen = False
                touch_feedback_msg = "Fullscreen off"
            else:
                opt.fullscreen = True
                touch_feedback_msg = "Fullscreen on"
            touch_feedback_timer = 60
        elif x < 3 * w_main / 4:  # Right middle quarter - toggle reverse IQ
            if opt.rev_iq:
                opt.rev_iq = False
                touch_feedback_msg = "Reverse IQ off"
            else:
                opt.rev_iq = True
                touch_feedback_msg = "Reverse IQ on"
            touch_feedback_timer = 60
        else:  # Right quarter - reset all settings
            # Reset display settings
            sp_min, sp_max = sp_min_def, sp_max_def
            mygraticule.set_range(sp_min, sp_max)
            surf_2d_graticule = mygraticule.make()
            if opt.waterfall:
                v_min, v_max = mywf.reset_range()
            touch_feedback_msg = "All settings reset"
            touch_feedback_timer = 60

def handle_touch_tap(x, y):
    """Handle tap gestures for quick frequency presets
    Args:
        x: x position of tap
        y: y position of tap
    """
    global touch_feedback_msg, touch_feedback_timer, rigfreq_request, dataIn, mysi570, h_2d
    
    # Define frequency preset zones based on screen position
    if y < h_2d / 3:  # Top third - high frequency presets
        if opt.control == 'rtl':
            preset_freq = 146.0e6  # 146 MHz
            dataIn.rtl.center_freq = preset_freq
            touch_feedback_msg = f"Preset: 146.0 MHz"
        elif opt.control == 'si570':
            preset_freq = 14.0  # 14 MHz
            mysi570.setFreqByValue(preset_freq)
            touch_feedback_msg = f"Preset: 14.0 MHz"
        elif opt.hamlib:
            rigfreq_request = 14000.0  # 14 MHz
            touch_feedback_msg = f"Preset: 14.0 MHz"
        touch_feedback_timer = 60
        
    elif y < 2 * h_2d / 3:  # Middle third - mid frequency presets
        if opt.control == 'rtl':
            preset_freq = 50.0e6  # 50 MHz
            dataIn.rtl.center_freq = preset_freq
            touch_feedback_msg = f"Preset: 50.0 MHz"
        elif opt.control == 'si570':
            preset_freq = 7.0  # 7 MHz
            mysi570.setFreqByValue(preset_freq)
            touch_feedback_msg = f"Preset: 7.0 MHz"
        elif opt.hamlib:
            rigfreq_request = 7000.0  # 7 MHz
            touch_feedback_msg = f"Preset: 7.0 MHz"
        touch_feedback_timer = 60
        
    else:  # Bottom third - low frequency presets
        if opt.control == 'rtl':
            preset_freq = 30.0e6  # 30 MHz
            dataIn.rtl.center_freq = preset_freq
            touch_feedback_msg = f"Preset: 30.0 MHz"
        elif opt.control == 'si570':
            preset_freq = 3.5  # 3.5 MHz
            mysi570.setFreqByValue(preset_freq)
            touch_feedback_msg = f"Preset: 3.5 MHz"
        elif opt.hamlib:
            rigfreq_request = 3500.0  # 3.5 MHz
            touch_feedback_msg = f"Preset: 3.5 MHz"
            touch_feedback_timer = 60

def handle_touch_frequency_step_adjustment(x, y):
    """Handle touch-based frequency step adjustment
    Args:
        x: x position of touch
        y: y position of touch
    """
    global touch_freq_step, touch_freq_step_coarse, touch_feedback_msg, touch_feedback_timer
    
    # Define frequency step adjustment zones based on screen position
    if x < w_main / 2:  # Left half - fine adjustment
        touch_freq_step = opt.touch_sensitivity
        touch_feedback_msg = f"Fine step: {touch_freq_step:.1f} kHz/pixel"
        touch_feedback_timer = 60
    else:  # Right half - coarse adjustment
        touch_freq_step = opt.touch_coarse_sensitivity
        touch_feedback_msg = f"Coarse step: {touch_freq_step:.1f} kHz/pixel"
        touch_feedback_timer = 60

def handle_touch_lagfix_adjustment(x, y):
    """Handle touch-based lagfix adjustment
    Args:
        x: x position of touch
        y: y position of touch
    """
    global touch_feedback_msg, touch_feedback_timer
    
    # Define lagfix adjustment zones based on screen position
    if x < w_main / 2:  # Left half - disable lagfix
        opt.lagfix = False
        touch_feedback_msg = "Lagfix: OFF"
        touch_feedback_timer = 60
    else:  # Right half - enable lagfix
        opt.lagfix = True
        touch_feedback_msg = "Lagfix: ON"
        touch_feedback_timer = 60

def handle_touch_skip_adjustment(x, y):
    """Handle touch-based skip adjustment
    Args:
        x: x position of touch
        y: y position of touch
    """
    global touch_feedback_msg, touch_feedback_timer, h_2d
    
    # Define skip adjustment zones based on screen position
    if x < w_main / 3:  # Left third - decrease skip
        if opt.skip > 0:
            opt.skip = opt.skip - 1
            touch_feedback_msg = f"Skip: {opt.skip}"
        else:
            touch_feedback_msg = "Min skip reached"
        touch_feedback_timer = 60
    elif x < 2 * w_main / 3:  # Middle third - reset skip
        opt.skip = 0
        touch_feedback_msg = f"Skip reset: {opt.skip}"
        touch_feedback_timer = 60
    else:  # Right third - increase skip
        if opt.skip < 10:
            opt.skip = opt.skip + 1
            touch_feedback_msg = f"Skip: {opt.skip}"
        else:
            touch_feedback_msg = "Max skip reached"
        touch_feedback_timer = 60

def handle_touch_pulse_clip_adjustment(x, y):
    """Handle touch-based pulse clip adjustment
    Args:
        x: x position of touch
        y: y position of touch
    """
    global touch_feedback_msg, touch_feedback_timer, h_2d
    
    # Define pulse clip adjustment zones based on screen position
    if x < w_main / 3:  # Left third - decrease pulse clip threshold
        if opt.pulse > 1:
            opt.pulse = opt.pulse - 1
            touch_feedback_msg = f"Pulse clip: {opt.pulse}"
        else:
            touch_feedback_msg = "Min pulse clip reached"
        touch_feedback_timer = 60
    elif x < 2 * w_main / 3:  # Middle third - reset pulse clip threshold
        opt.pulse = 10
        touch_feedback_msg = f"Pulse clip reset: {opt.pulse}"
        touch_feedback_timer = 60
    else:  # Right third - increase pulse clip threshold
        if opt.pulse < 50:
            opt.pulse = opt.pulse + 1
            touch_feedback_msg = f"Pulse clip: {opt.pulse}"
        else:
            touch_feedback_msg = "Max pulse clip reached"
        touch_feedback_timer = 60

def handle_touch_waterfall_accumulation_adjustment(x, y):
    """Handle touch-based waterfall accumulation adjustment
    Args:
        x: x position of touch
        y: y position of touch
    """
    global touch_feedback_msg, touch_feedback_timer, h_2d
    
    # Define waterfall accumulation adjustment zones based on screen position
    if x < w_main / 3:  # Left third - decrease accumulation
        if opt.waterfall_accumulation > 1:
            opt.waterfall_accumulation = opt.waterfall_accumulation - 1
            touch_feedback_msg = f"WF acc: {opt.waterfall_accumulation}"
        else:
            touch_feedback_msg = "Min accumulation reached"
        touch_feedback_timer = 60
    elif x < 2 * w_main / 3:  # Middle third - reset accumulation
        opt.waterfall_accumulation = 4
        touch_feedback_msg = f"WF acc reset: {opt.waterfall_accumulation}"
        touch_feedback_timer = 60
    else:  # Right third - increase accumulation
        if opt.waterfall_accumulation < 20:
            opt.waterfall_accumulation = opt.waterfall_accumulation + 1
            touch_feedback_msg = f"WF acc: {opt.waterfall_accumulation}"
        else:
            touch_feedback_msg = "Max accumulation reached"
        touch_feedback_timer = 60

def handle_touch_waterfall_palette_adjustment(x, y):
    """Handle touch-based waterfall palette adjustment
    Args:
        x: x position of touch
        y: y position of touch
    """
    global touch_feedback_msg, touch_feedback_timer, h_2d
    
    # Define waterfall palette adjustment zones based on screen position
    if x < w_main / 3:  # Left third - previous palette
        if opt.waterfall_palette > 1:
            opt.waterfall_palette = opt.waterfall_palette - 1
            touch_feedback_msg = f"Palette: {opt.waterfall_palette}"
        else:
            touch_feedback_msg = "Min palette reached"
        touch_feedback_timer = 60
    elif x < 2 * w_main / 3:  # Middle third - reset palette
        opt.waterfall_palette = 2
        touch_feedback_msg = f"Palette reset: {opt.waterfall_palette}"
        touch_feedback_timer = 60
    else:  # Right third - next palette
        if opt.waterfall_palette < 5:
            opt.waterfall_palette = opt.waterfall_palette + 1
            touch_feedback_msg = f"Palette: {opt.waterfall_palette}"
        else:
            touch_feedback_msg = "Max palette reached"
        touch_feedback_timer = 60

def handle_touch_buffer_adjustment(x, y):
    """Handle touch-based buffer adjustment
    Args:
        x: x position of touch
        y: y position of touch
    """
    global touch_feedback_msg, touch_feedback_timer, h_2d
    
    # Define buffer adjustment zones based on screen position
    if x < w_main / 3:  # Left third - decrease buffer count
        if opt.buffers > 1:
            opt.buffers = opt.buffers - 1
            touch_feedback_msg = f"Buffers: {opt.buffers}"
        else:
            touch_feedback_msg = "Min buffer count reached"
        touch_feedback_timer = 60
    elif x < 2 * w_main / 3:  # Middle third - reset buffer count
        opt.buffers = 12
        touch_feedback_msg = f"Buffers reset: {opt.buffers}"
        touch_feedback_timer = 60
    else:  # Right third - increase buffer count
        if opt.buffers < 50:
            opt.buffers = opt.buffers + 1
            touch_feedback_msg = f"Buffers: {opt.buffers}"
        else:
            touch_feedback_msg = "Max buffer count reached"
        touch_feedback_timer = 60

def handle_touch_fft_size_adjustment(x, y):
    """Handle touch-based FFT size adjustment
    Args:
        x: x position of touch
        y: y position of touch
    """
    global touch_feedback_msg, touch_feedback_timer, w_spectra, h_2d, myDSP
    
    # Define FFT size adjustment zones based on screen position
    if x < w_main / 3:  # Left third - decrease FFT size
        if opt.size > 64:
            opt.size = opt.size // 2
            myDSP.update_window()
            touch_feedback_msg = f"FFT size: {opt.size}"
        else:
            touch_feedback_msg = "Min FFT size reached"
        touch_feedback_timer = 60
    elif x < 2 * w_main / 3:  # Middle third - reset FFT size
        opt.size = 384
        myDSP.update_window()
        touch_feedback_msg = f"FFT size reset: {opt.size}"
        touch_feedback_timer = 60
    else:  # Right third - increase FFT size
        if opt.size < 1024 and opt.size * 2 <= w_spectra:
            opt.size = opt.size * 2
            myDSP.update_window()
            touch_feedback_msg = f"FFT size: {opt.size}"
        else:
            touch_feedback_msg = "Max FFT size reached"
        touch_feedback_timer = 60

def handle_touch_sample_rate_adjustment(x, y):
    """Handle touch-based sample rate adjustment
    Args:
        x: x position of touch
        y: y position of touch
    """
    global touch_feedback_msg, touch_feedback_timer, h_2d
    
    # Define sample rate adjustment zones based on screen position
    if x < w_main / 3:  # Left third - decrease sample rate
        if opt.sample_rate > 48000:
            opt.sample_rate = opt.sample_rate // 2
            touch_feedback_msg = f"Sample rate: {opt.sample_rate} Hz"
        else:
            touch_feedback_msg = "Min sample rate reached"
        touch_feedback_timer = 60
    elif x < 2 * w_main / 3:  # Middle third - reset sample rate
        if opt.source == 'rtl':
            opt.sample_rate = 1024000
        else:
            opt.sample_rate = 48000
        touch_feedback_msg = f"Sample rate reset: {opt.sample_rate} Hz"
        touch_feedback_timer = 60
    else:  # Right third - increase sample rate
        if opt.sample_rate < 2048000:
            opt.sample_rate = opt.sample_rate * 2
            touch_feedback_msg = f"Sample rate: {opt.sample_rate} Hz"
        else:
            touch_feedback_msg = "Max sample rate reached"
        touch_feedback_timer = 60

def handle_touch_gain_adjustment(x, y):
    """Handle touch-based gain adjustment
    Args:
        x: x position of touch
        y: y position of touch
    """
    global touch_feedback_msg, touch_feedback_timer, dataIn, h_2d
    
    # Define gain adjustment zones based on screen position
    if x < w_main / 2:  # Left half - decrease gain
        if opt.source == 'rtl':
            current_gain = dataIn.rtl.get_gain()
            new_gain = max(0, current_gain - 5)
            dataIn.rtl.set_gain(new_gain)
            touch_feedback_msg = f"Gain: {new_gain} dB"
        else:
            touch_feedback_msg = "Gain control not available"
        touch_feedback_timer = 60
    else:  # Right half - increase gain
        if opt.source == 'rtl':
            current_gain = dataIn.rtl.get_gain()
            new_gain = min(50, current_gain + 5)
            dataIn.rtl.set_gain(new_gain)
            touch_feedback_msg = f"Gain: {new_gain} dB"
        else:
            touch_feedback_msg = "Gain control not available"
        touch_feedback_timer = 60

def handle_touch_frequency_band_switch(x, y):
    """Handle touch-based frequency band switching
    Args:
        x: x position of touch
        y: y position of touch
    """
    global touch_feedback_msg, touch_feedback_timer, rigfreq_request, dataIn, mysi570, h_2d
    
    # Define frequency band zones based on screen position
    if y < h_2d / 4:  # Top quarter - HF bands
        if opt.control == 'rtl':
            dataIn.rtl.center_freq = 14.0e6  # 14 MHz
            touch_feedback_msg = "HF band (14 MHz)"
        elif opt.control == 'si570':
            mysi570.setFreqByValue(14.0)
            touch_feedback_msg = "HF band (14 MHz)"
        elif opt.hamlib:
            rigfreq_request = 14000.0
            touch_feedback_msg = "HF band (14 MHz)"
        touch_feedback_timer = 60
    elif y < 2 * h_2d / 4:  # Second quarter - VHF bands
        if opt.control == 'rtl':
            dataIn.rtl.center_freq = 146.0e6  # 146 MHz
            touch_feedback_msg = "VHF band (146 MHz)"
        elif opt.control == 'si570':
            mysi570.setFreqByValue(146.0)
            touch_feedback_msg = "VHF band (146 MHz)"
        elif opt.hamlib:
            rigfreq_request = 146000.0
            touch_feedback_msg = "VHF band (146 MHz)"
        touch_feedback_timer = 60
    elif y < 3 * h_2d / 4:  # Third quarter - UHF bands
        if opt.control == 'rtl':
            dataIn.rtl.center_freq = 440.0e6  # 440 MHz
            touch_feedback_msg = "UHF band (440 MHz)"
        elif opt.control == 'si570':
            mysi570.setFreqByValue(440.0)
            touch_feedback_msg = "UHF band (440 MHz)"
        elif opt.hamlib:
            rigfreq_request = 440000.0
            touch_feedback_msg = "UHF band (440 MHz)"
        touch_feedback_timer = 60
    else:  # Bottom quarter - LF bands
        if opt.control == 'rtl':
            dataIn.rtl.center_freq = 3.5e6  # 3.5 MHz
            touch_feedback_msg = "LF band (3.5 MHz)"
        elif opt.control == 'si570':
            mysi570.setFreqByValue(3.5)
            touch_feedback_msg = "LF band (3.5 MHz)"
        elif opt.hamlib:
            rigfreq_request = 3500.0
            touch_feedback_msg = "LF band (3.5 MHz)"
        touch_feedback_timer = 60

def handle_touch_display_mode_switch(x, y):
    """Handle touch-based display mode switching
    Args:
        x: x position of touch
        y: y position of touch
    """
    global touch_feedback_msg, touch_feedback_timer
    
    # Define display mode zones based on screen position
    if x < w_main / 3:  # Left third - spectrum only
        opt.waterfall = False
        touch_feedback_msg = "Spectrum only mode"
        touch_feedback_timer = 60
    elif x < 2 * w_main / 3:  # Middle third - spectrum + waterfall
        opt.waterfall = True
        touch_feedback_msg = "Spectrum + waterfall mode"
        touch_feedback_timer = 60
    else:  # Right third - waterfall only
        opt.waterfall = True
        # Could add a waterfall-only mode here if needed
        touch_feedback_msg = "Waterfall mode"
        touch_feedback_timer = 60

def draw_touch_zones(surface):
    """Draw visual indicators for touch zones on the screen (landscape orientation)
    Args:
        surface: pygame surface to draw on
    """
    global h_2d, w_main, BLUE_GRAY
    if opt.control in ['rtl', 'si570', 'hamlib']:
        # Draw zone boundaries for landscape orientation
        # Frequency zones are now vertical (Y-axis)
        zone1_y = h_2d / 3
        zone2_y = 2 * h_2d / 3
        
        # Draw vertical lines to separate frequency zones
        pg.draw.line(surface, BLUE_GRAY, (zone1_y, 0), (zone1_y, w_main), 2)
        pg.draw.line(surface, BLUE_GRAY, (zone2_y, 0), (zone2_y, w_main), 2)
        
        # Add zone labels rotated for landscape
        font = pg.font.SysFont('sans', 10)
        
        # Draw rotated frequency zone labels
        draw_rotated_text(surface, "High Freq", font, BLUE_GRAY, (zone1_y/2, 20), 270)
        draw_rotated_text(surface, "Mid Freq", font, BLUE_GRAY, (zone1_y + zone1_y/2, 20), 270)
        draw_rotated_text(surface, "Low Freq", font, BLUE_GRAY, (zone2_y + zone1_y/2, 20), 270)
        
        # Draw dB scale zones (horizontal for landscape)
        db_zone1 = w_main / 3
        db_zone2 = 2 * w_main / 3
        
        # Draw horizontal lines for dB zones
        pg.draw.line(surface, BLUE_GRAY, (db_zone1, 0), (db_zone1, h_2d), 1)
        pg.draw.line(surface, BLUE_GRAY, (db_zone2, 0), (db_zone2, h_2d), 1)
        
        # Add rotated dB zone labels
        draw_rotated_text(surface, "Upper dB", font, BLUE_GRAY, (db_zone1/2, h_2d - 20), 270)
        draw_rotated_text(surface, "Lower dB", font, BLUE_GRAY, (db_zone2 + db_zone2/2, h_2d - 20), 270)

def draw_rotated_text(surface, text, font, color, position, angle=90):
    """Draw text rotated by the specified angle
    Args:
        surface: pygame surface to draw on
        text: text string to render
        font: pygame font object
        color: text color
        position: (x, y) position for the text
        angle: rotation angle in degrees (default 90 for landscape)
    """
    # Render the text
    text_surface = font.render(text, True, color)
    
    # Rotate the text surface
    rotated_surface = pg.transform.rotate(text_surface, angle)
    
    # Get the rectangle of the rotated surface
    rotated_rect = rotated_surface.get_rect()
    
    # Position the rotated text
    rotated_rect.center = position
    
    # Draw the rotated text
    surface.blit(rotated_surface, rotated_rect)

def draw_touch_feedback(surface):
    """Draw touch feedback messages with fade-out effect
    Args:
        surface: pygame surface to draw on
    """
    global touch_feedback_msg, touch_feedback_timer, touch_feedback_alpha, dataIn, mysi570, rigfreq, sp_min, sp_max
    
    if touch_feedback_msg and touch_feedback_timer > 0:
        # Create font for feedback
        font = pg.font.SysFont('sans', 18)
        
        # Render text with current alpha
        text_surface = font.render(touch_feedback_msg, True, (255, 255, 255))
        text_surface.set_alpha(touch_feedback_alpha)
        
        # Position text in center of screen for landscape orientation
        text_rect = text_surface.get_rect()
        text_rect.center = (w_main // 2, h_2d // 2)
        
        # Draw background rectangle for better visibility
        bg_rect = text_rect.inflate(20, 10)
        bg_surface = pg.Surface(bg_rect.size, pg.SRCALPHA)
        bg_surface.fill((0, 0, 0, min(180, touch_feedback_alpha)))
        surface.blit(bg_surface, bg_rect)
        
        # Draw text
        surface.blit(text_surface, text_rect)
        
        # Update alpha for fade effect
        if touch_feedback_timer <= 10:  # Start fading in last 10 frames
            touch_feedback_alpha = max(0, touch_feedback_alpha - 25)
        else:
            touch_feedback_alpha = min(255, touch_feedback_alpha + 25)
        
        touch_feedback_timer -= 1
    
    # Show real-time values during touch
    if touch_active:
        # Create font for real-time display
        font = pg.font.SysFont('sans', 14)
        
        # Get current frequency
        if opt.control == 'rtl':
            current_freq = dataIn.rtl.get_center_freq() / 1e6  # Convert to MHz
            freq_text = f"Freq: {current_freq:.3f} MHz"
        elif opt.control == 'si570':
            current_freq = mysi570.getFreqByValue()
            freq_text = f"Freq: {current_freq:.3f} MHz"
        elif opt.hamlib and 'hamlib_available' in globals() and hamlib_available:
            freq_text = f"Freq: {rigfreq:.1f} kHz"
        else:
            freq_text = "Freq: N/A"
        
        # Get current dB values
        db_text = f"dB: {sp_min} to {sp_max}"
        
        # Draw rotated text for landscape orientation
        draw_rotated_text(surface, freq_text, font, (255, 255, 0), (50, 50), 270)  # Yellow
        draw_rotated_text(surface, db_text, font, (0, 255, 255), (50, 100), 270)   # Cyan

def handle_waterfall_touch_controls(x, y, dx, dy):
    """Handle touch controls specific to waterfall display
    Args:
        x: current x position
        y: current y position
        dx: horizontal movement
        dy: vertical movement
    """
    global v_min, v_max, touch_feedback_msg, touch_feedback_timer, mywf
    
    if opt.waterfall:
        # Adjust waterfall palette with HORIZONTAL movement (landscape orientation)
        if abs(dx) > 5:
            if dx > 0:  # Moving right - increase upper threshold
                if v_max < -10:
                    v_max += 5
                    mywf.set_range(v_min, v_max)
                    touch_feedback_msg = f"WF upper: {v_max} dB"
                    touch_feedback_timer = 30
            else:  # Moving left - decrease upper threshold
                if v_max > v_min + 20:
                    v_max -= 5
                    mywf.set_range(v_min, v_max)
                    touch_feedback_msg = f"WF upper: {v_max} dB"
                    touch_feedback_timer = 30
        
        # Adjust waterfall palette with VERTICAL movement (landscape orientation)
        if abs(dy) > 5:
            if dy > 0:  # Moving down - increase lower threshold
                if v_min < v_max - 20:
                    v_min += 5
                    mywf.set_range(v_min, v_max)
                    touch_feedback_msg = f"WF lower: {v_min} dB"
                    touch_feedback_timer = 30
            else:  # Moving up - decrease lower threshold
                if v_min > -130:
                    v_min -= 5
                    mywf.set_range(v_min, v_max)
                    touch_feedback_msg = f"WF lower: {v_min} dB"
                    touch_feedback_timer = 30
        
        # Adjust waterfall accumulation with diagonal movement (landscape orientation)
        if abs(dx) > 10 and abs(dy) > 10:
            if dx > 0 and dy > 0:  # Diagonal down-right - increase accumulation
                if opt.waterfall_accumulation < 20:
                    opt.waterfall_accumulation += 1
                    touch_feedback_msg = f"WF acc: {opt.waterfall_accumulation}"
                    touch_feedback_timer = 30
            elif dx < 0 and dy < 0:  # Diagonal up-left - decrease accumulation
                if opt.waterfall_accumulation > 1:
                    opt.waterfall_accumulation -= 1
                    touch_feedback_msg = f"WF acc: {opt.waterfall_accumulation}"
                    touch_feedback_timer = 30

def handle_spectrum_touch_controls(x, y, dx, dy):
    """Handle touch controls specific to spectrum display
    Args:
        x: current x position
        y: current y position
        dx: horizontal movement
        dy: vertical movement
    """
    global sp_min, sp_max, touch_feedback_msg, touch_feedback_timer, mygraticule, surf_2d_graticule, w_spectra, myDSP
    
    # Adjust spectrum dB limits with HORIZONTAL movement (landscape orientation)
    if abs(dx) > 5:
        if dx > 0:  # Moving right - increase upper limit
            if sp_max < 0:
                sp_max += 5
                mygraticule.set_range(sp_min, sp_max)
                surf_2d_graticule = mygraticule.make()
                touch_feedback_msg = f"Upper dB: {sp_max} dB"
                touch_feedback_timer = 30
        else:  # Moving left - decrease upper limit
            if sp_max > -130 and sp_max > sp_min + 10:
                sp_max -= 5
                mygraticule.set_range(sp_min, sp_max)
                surf_2d_graticule = mygraticule.make()
                touch_feedback_msg = f"Upper dB: {sp_max} dB"
                touch_feedback_timer = 30
    
    # Adjust spectrum dB limits with VERTICAL movement (landscape orientation)
    if abs(dy) > 5:
        if dy > 0:  # Moving down - increase lower limit
            if sp_min < sp_max - 10:
                sp_min += 5
                mygraticule.set_range(sp_min, sp_max)
                surf_2d_graticule = mygraticule.make()
                touch_feedback_msg = f"Lower dB: {sp_min} dB"
                touch_feedback_timer = 30
        else:  # Moving up - decrease lower limit
            if sp_min > -140:
                sp_min -= 5
                mygraticule.set_range(sp_min, sp_max)
                surf_2d_graticule = mygraticule.make()
                touch_feedback_msg = f"Lower dB: {sp_min} dB"
                touch_feedback_timer = 30
        
        # Adjust FFT size with diagonal movement (landscape orientation)
        if abs(dx) > 10 and abs(dy) > 10:
            if dx > 0 and dy < 0:  # Diagonal up-right - increase FFT size
                new_size = opt.size * 2
                if new_size <= w_spectra and new_size <= 1024:
                    opt.size = new_size
                    myDSP.update_window()
                    touch_feedback_msg = f"FFT size: {opt.size}"
                    touch_feedback_timer = 30
            elif dx < 0 and dy > 0:  # Diagonal down-left - decrease FFT size
                new_size = opt.size // 2
                if new_size >= 64:
                    opt.size = new_size
                    myDSP.update_window()
                    touch_feedback_msg = f"FFT size: {opt.size}"
                    touch_feedback_timer = 30

class LED(object):
    """ Make an LED indicator surface in pygame environment. 
        Does not include title
    """
    def __init__(self, width):
        """ width = pixels width (& height)
            colors = dictionary with color_values and PyGame Color specs
        """
        self.surface = pg.Surface((width, width))
        self.wd2 = width/2
        return

    def get_LED_surface(self, color):
        """ Set LED surface to requested color
            Return square surface ready to blit
        """
        self.surface.fill(BGCOLOR)
        # Always make full-size black circle with no fill.
        pg.draw.circle(self.surface,BLACK,(self.wd2,self.wd2),self.wd2,2)
        if color == None:
            return self.surface
        # Make inset filled color circle.
        pg.draw.circle(self.surface,color,(self.wd2,self.wd2),self.wd2-2,0)
        return self.surface

class Graticule(object):
    """ Create a pygame surface with freq / power (dB) grid
        and units.
        input: options, pg font, graticule height, width, line color, 
            and text color
    """
    def __init__(self, opt, font, h, w, color_l, color_t):
        self.opt = opt
        self.sp_max = opt.sp_max #-20   # default max value (dB)
        self.sp_min = opt.sp_min #-120  # default min value
        self.font = font    # font to use for text
        self.h = h          # height of graph area
        self.w = w          # width
        self.color_l = color_l    # color for lines
        self.color_t = color_t    # color for text
        self.surface = pg.Surface((self.w, self.h))
        return
        
    def make(self):
        """ Make or re-make the graticule.
            Returns pygame surface
        """
        self.surface.fill(BLACK)
        # yscale is screen units per dB
        yscale = float(self.h)/(self.sp_max-self.sp_min)
        # Define vertical dB scale - draw line each 10 dB.
        for attn in range(self.sp_min, self.sp_max, 10):
            yattn = ((attn - self.sp_min) * yscale) + 3.
            yattnflip = self.h - yattn    # screen y coord increases downward
            # Draw a single line, dark red.
            pg.draw.line(self.surface, self.color_l, (0, yattnflip), 
                                        (self.w, yattnflip))
            # Render and blit the dB value at left, just above line
            self.surface.blit(self.font.render("%3d" % attn, 1, self.color_t), 
                                        (5, yattnflip-12))

        # add unit (dB) to topmost label        
        ww, hh = self.font.size("%3d" % attn)
        self.surface.blit(self.font.render("dB",  1, self.color_t), 
                                        (5+ww, yattnflip-12))

        # Define freq. scale - draw vert. line at convenient intervals
        frq_range = float(self.opt.sample_rate)/1000.    # kHz total bandwidth
        xscale = self.w/frq_range               # pixels/kHz x direction
        srate2 = frq_range/2                    # plus or minus kHz
        # Choose the best tick that will work with RTL or sound cards.
        for xtick_max in [ 800, 400, 200, 100, 80, 40, 20, 10 ]:
            if xtick_max < srate2:
                break
        ticks = [ -xtick_max, -xtick_max/2, 0, xtick_max/2, xtick_max ]
        for offset in ticks:
            x = offset*xscale + self.w/2
            pg.draw.line(self.surface, self.color_l, (x, 0), (x, self.h))
            fmt = "%d kHz" if offset == 0 else "%+3d"
            self.surface.blit(self.font.render(fmt % offset, 1, self.color_t), 
                                        (x+2, 0))
        return self.surface
        
    def set_range(self, sp_min, sp_max):
        """ Set desired range for vertical scale in dB, min. and max.
            0 dB is maximum theoretical response for 16 bit sampling.
            Lines are always drawn at 10 dB intervals.
        """
        if not sp_max > sp_min:
            print("Invalid dB scale setting requested!")
            quit_all()
        self.sp_max = sp_max
        self.sp_min = sp_min
        return

# THREAD: Hamlib, checking Rx frequency, and changing if requested.
if opt.hamlib:
    import Hamlib
    rigfreq_request = None
    rigfreq = 7.0e6             # something reasonable to start
    def updatefreq(interval, rig):
        """ Read/set rig frequency via Hamlib.
            Interval defines repetition time (float secs)
            Return via global variable rigfreq (float kHz)
            To be run as thread.
            (All Hamlib I/O is done through this thread.)
        """
        global rigfreq, rigfreq_request
        try:
            rigfreq = float(rig.get_freq()) * 0.001     # freq in kHz
            while True:                     # forever!
                # With KX3 @ 38.4 kbs, get_freq takes 100-150 ms to complete
                # If a new vfo setting is desired, we will have rigfreq_request
                # set to the new frequency, otherwise = None.
                if rigfreq_request:         # ordering of loop speeds up freq change
                    if rigfreq_request != rigfreq:
                        try:
                            rig.set_freq(int(rigfreq_request*1000))
                        except TypeError as e:
                            print(f"Hamlib set_freq error: {e}")
                            print(f"Trying alternative method...")
                            try:
                                # Try with string frequency
                                rig.set_freq(str(int(rigfreq_request*1000)))
                            except Exception as e2:
                                print(f"Alternative method also failed: {e2}")
                                print(f"rigfreq_request: {rigfreq_request}, calculated: {int(rigfreq_request*1000)}")
                        rigfreq_request = None
                rigfreq = float(rig.get_freq()) * 0.001     # freq in kHz
                time.sleep(interval)
        except Exception as e:
            print(f"Hamlib thread error: {e}")
            global hamlib_available
            hamlib_available = False
            opt.control = "none"

# THREAD: CPU load checking, monitoring cpu stats.
cpu_usage = [0., 0., 0.]
def cpu_load(interval):
    """ Check CPU user and system time usage, along with load average.
        User & system reported as fraction of wall clock time in
        global variable cpu_usage.
        Interval defines sleep time between checks (float secs).
        To be run as thread.
    """
    global cpu_usage
    times_store = np.array(os.times())
    # Will return: fraction usr time, sys time, and 1-minute load average
    cpu_usage = [0., 0., os.getloadavg()[0]]
    while True:
        time.sleep(interval)
        times = np.array(os.times())
        dtimes = times - times_store    # difference since last loop
        usr = dtimes[0]/dtimes[4]       # fraction, 0 - 1
        sys = dtimes[1]/dtimes[4]
        times_store = times
        cpu_usage = [usr, sys, os.getloadavg()[0]]

# Screen setup parameters

if opt.lcd4:                        # setup for directfb (non-X) graphics
    SCREEN_SIZE = (400,1280)         # default size for the 4" LCD (480x272)
    SCREEN_MODE = pg.FULLSCREEN
    # If we are root, we can set up LCD4 brightness.
    brightness = str(min(100, max(0, opt.lcd4_brightness)))  # validated string
    # Find path of script (same directory as iq.py) and append brightness value
    cmd = os.path.join( os.path.split(sys.argv[0])[0], "lcd4_brightness.sh") \
        + " %s" % brightness
    # (The subprocess script is a no-op if we are not root.)
    subprocess.call(cmd, shell=True)    # invoke shell script
else:
    SCREEN_MODE = pg.FULLSCREEN if opt.fullscreen else 0
    SCREEN_SIZE = (400,1280) if opt.waterfall \
                     else (400,1280) # NB: graphics may not scale well
WF_LINES = 100                      # How many lines to use in the waterfall

# Initialize pygame (pg)
# We should not use pg.init(), because we don't want pg audio functions.
pg.display.init()
# pg.mouse.set_visible(False)
pg.font.init()

# Define the main window surface
surf_main = pg.display.set_mode([400,1280], SCREEN_MODE)
w_main = 1280

# derived parameters
w_spectra = w_main # -10  don't need         # Allow a small margin, left and right
w_middle = w_spectra/2          # mid point of spectrum
x_spectra = (w_main-w_spectra) / 2.0    # x coord. of spectrum on screen

h_2d = 266 if opt.waterfall \
            else SCREEN_SIZE[1]         # height of 2d spectrum display
#h_2d -= 25 # compensate for LCD4 overscan?
y_2d = 0 # y position of 2d disp. (screen top = 0)

# NB: transform size must be <= w_spectra.  I.e., need at least one
# pixel of width per data point.  Otherwise, waterfall won't work, etc.
if opt.size > w_spectra:
    for n in [1024, 512, 256, 128]:
        if n <= w_spectra:
            print("*** Size was reset from %d to %d." % (opt.size, n))
            opt.size = n    # Force size to be 2**k (ok, reasonable choice?)
            break
chunk_size = opt.buffers * opt.size # No. samples per chunk (pyaudio callback)
chunk_time = float(chunk_size) / opt.sample_rate

myDSP = dsp.DSP(opt)            # Establish DSP logic

# Surface for the 2d spectrum
surf_2d = pg.Surface((w_spectra, h_2d))             # Initialized to black
surf_2d_graticule = pg.Surface((w_spectra, h_2d))   # to hold fixed graticule

# define two LED widgets
led_urun = LED(10)
led_clip = LED(10)

# Waterfall geometry
h_wf = 180         # Height of waterfall (3d spectrum)
y_wf = 220              # Position just below 2d surface

# Surface for waterfall (3d) spectrum
surf_wf = pg.Surface((w_spectra, h_wf))

pg.display.set_caption(opt.ident)       # Title for main window

# Establish fonts for screen text.
lgfont = pg.font.SysFont('sans', 16)
lgfont_ht = lgfont.get_linesize()       # text height
medfont = pg.font.SysFont('sans', 12)
medfont_ht = medfont.get_linesize()
smfont = pg.font.SysFont('mono', 9)
smfont_ht = smfont.get_linesize()

# Define the size of a unit pixel in the waterfall
wf_pixel_size = (w_spectra/opt.size+1, h_wf/WF_LINES)

# min, max dB for wf palette
v_min, v_max = opt.v_min, opt.v_max     # lower/higher end (dB)
nsteps = 50                             # number of distinct colors

if opt.waterfall:
    # Instantiate the waterfall and palette data
    mywf = wf.Wf(opt, v_min, v_max, nsteps, wf_pixel_size)

if (opt.control == "si570") and opt.hamlib:
    print("Warning: Hamlib requested with si570.  Si570 wins! No Hamlib.")
if opt.hamlib and (opt.control != "si570"):
    try:
        import Hamlib
        # start up Hamlib rig connection
        Hamlib.rig_set_debug (Hamlib.RIG_DEBUG_NONE)
        rig = Hamlib.Rig(opt.hamlib_rigtype)
        rig.set_conf ("rig_pathname",opt.hamlib_device)
        rig.set_conf ("retry","5")
        rig.open ()
        
        # Create thread for Hamlib freq. checking.  
        # Helps to even out the loop timing, maybe.
        hl_thread = threading.Thread(target=updatefreq, 
                            args = (opt.hamlib_interval, rig))
        hl_thread.daemon = True
        hl_thread.start()
        print("Hamlib thread started.")
        hamlib_available = True
    except Exception as e:
        print(f"Hamlib initialization failed: {e}")
        print("Falling back to no frequency control")
        opt.control = "none"
        hamlib_available = False
else:
    print("Hamlib not requested.")
    hamlib_available = False

# Create thread for cpu load monitor
lm_thread = threading.Thread(target=cpu_load, args = (opt.cpu_load_interval,))
lm_thread.daemon = True
lm_thread.start()
print("CPU monitor thread started.")

# Create graticule providing 2d graph calibration.
mygraticule = Graticule(opt, medfont, h_2d, w_spectra, GRAT_COLOR, GRAT_COLOR_2)
sp_min, sp_max  =  sp_min_def, sp_max_def  =  opt.sp_min, opt.sp_max
mygraticule.set_range(sp_min, sp_max)
surf_2d_graticule = mygraticule.make()

# Pre-formatx "static" text items to save time in real-time loop
# Useful operating parameters
parms_msg = "Fs = %d Hz; Res. = %.1f Hz;" \
            " chans = %d; width = %d px; acc = %.3f sec" % \
      (opt.sample_rate, float(opt.sample_rate)/opt.size, opt.size, w_spectra, 
      float(opt.size*opt.buffers)/opt.sample_rate)
wparms, hparms = medfont.size(parms_msg)
parms_matter = pg.Surface((wparms, hparms) )
parms_matter.blit(medfont.render(parms_msg, 1, TCOLOR2), (0,0))

print("Update interval = %.2f ms" % float(1000*chunk_time))

# Initialize input mode, RTL or AF
# This starts the input stream, so place it close to start of main loop.
if opt.source=="rtl":             # input from RTL dongle (and freq control)
    import iq_rtl as rtl
    dataIn = rtl.RTL_In(opt)
# elif opt.source=='audio':         # input from audio card
#     import iq_af as af
#     mainqueueLock = af.queueLock    # queue and lock only for soundcard
#     dataIn = af.DataInput(opt)
elif opt.source=='audio':         # input from audio card
    dataIn = [0,0]                  # dummy data
else:
    print("unrecognized mode")
    quit_all()

if opt.control=="si570":
    import si570control
    mysi570 = si570control.Si570control()
    mysi570.setFreq(opt.si570_frequency / 1000.)    # Set starting freq.

# ** MAIN PROGRAM LOOP **

run_flag = True                 # set false to suspend for help screen etc.
info_phase = 0                 # > 0 --> show info overlays
info_counter = 0
tloop = 0.
t_last_data = 0
nframe = 0
t_frame0 = time.time()
led_overflow_ct = 0
startqueue = True
while True:

    nframe += 1                 # keep track of loop count FWIW

    # Each time through the main loop, we reconstruct the main screen

    surf_main.fill(BGCOLOR)     # Erase with background color
    
    # Draw touch zone indicators if frequency control is enabled
    if opt.control in ['rtl', 'si570'] or (opt.control == 'hamlib' and 'hamlib_available' in globals() and hamlib_available):
        draw_touch_zones(surf_main)
        print(f"Drawing touch zones for control: {opt.control}")
    else:
        print(f"Not drawing touch zones - control is: {opt.control}")

    # Each time through this loop, we receive an audio chunk, containing
    # multiple buffers.  The buffers have been transformed and the log power
    # spectra from each buffer will be provided in sp_log, which will be
    # plotted in the "2d" graph area.  After a number of log spectra are
    # displayed in the "2d" graph, a new line of the waterfall is generated.
    
    # Line of text with receiver center freq. if available
    showfreq = True
    if opt.control == "si570":
        msg = "%.3f kHz" % (mysi570.getFreqByValue() * 1000.) # freq/4 from Si570
    elif opt.hamlib and 'hamlib_available' in globals() and hamlib_available:
        msg = "%.3f kHz" % rigfreq   # take current rigfreq from hamlib thread
    elif opt.control=='rtl':
        msg = "%.3f MHz" % (dataIn.rtl.get_center_freq()/1.e6)
    else:
        showfreq = False

    if showfreq:
        # Center it and blit just above 2d display
        ww, hh = lgfont.size(msg)
        surf_main.blit(lgfont.render(msg, 1, BLACK, BGCOLOR), 
                            (w_middle + x_spectra - ww/2, y_2d-hh))
    
    # Show touch indicator if touch is active
    if touch_active:
        touch_msg = "TOUCH ACTIVE - Drag to change frequency"
        ww, hh = medfont.size(touch_msg)
        surf_main.blit(medfont.render(touch_msg, 1, RED, BGCOLOR), 
                            (w_main - ww - 10, 10))
    
    # Show touch feedback message
    if touch_feedback_timer > 0:
        ww, hh = medfont.size(touch_feedback_msg)
        surf_main.blit(medfont.render(touch_feedback_msg, 1, GREEN, BGCOLOR), 
                            (w_main - ww - 10, 30))
        touch_feedback_timer -= 1

    # show overflow & underrun indicators (for audio, not rtl)
    if opt.source=='audio':
        if af.led_underrun_ct > 0:        # underflow flag in af module
            sled = led_urun.get_LED_surface(RED)
            af.led_underrun_ct -= 1        # count down to extinguish
        else:
            sled = led_urun.get_LED_surface(None)   #off!
        msg = "Buffer underrun"
        ww, hh = medfont.size(msg)
        ww1 = SCREEN_SIZE[0]-ww-10
        surf_main.blit(medfont.render(msg, 1, BLACK, BGCOLOR), (ww1, y_2d-hh))
        surf_main.blit(sled, (ww1-15, y_2d-hh))
        if myDSP.led_clip_ct > 0:                   # overflow flag
            sled = led_clip.get_LED_surface(RED)
            myDSP.led_clip_ct -= 1
        else:
            sled = led_clip.get_LED_surface(None)   #off!
        msg = "Pulse clip"
        ww, hh = medfont.size(msg)
        surf_main.blit(medfont.render(msg, 1, BLACK, BGCOLOR), (25, y_2d-hh))
        surf_main.blit(sled, (10, y_2d-hh))

    if opt.source=='rtl':               # Input from RTL-SDR dongle
        iq_data_cmplx = dataIn.ReadSamples(chunk_size)
        if opt.rev_iq:                  # reverse spectrum?
            iq_data_cmplx = np.imag(iq_data_cmplx)+1j*np.real(iq_data_cmplx)
        #time.sleep(0.05)                # slow down if fast PC
        stats = [ 0, 0]                 # for now...
    else:                               # Input from audio card
        # In its separate thread, a chunk of audio data has accumulated.
        # When ready, pull log power spectrum data out of queue.
        my_in_data_s = dataIn.get_queued_data() # timeout protected

        # Convert string of 16-bit I,Q samples to complex floating
        iq_local = np.fromstring(my_in_data_s,dtype=np.int16).astype('float32')
        re_d = np.array(iq_local[1::2]) # right input (I)
        im_d = np.array(iq_local[0::2]) # left  input (Q)

        # The PCM290x chip has 1 lag offset of R wrt L channel. Fix, if needed.
        if opt.lagfix:
            im_d = np.roll(im_d, 1)
        # Get some stats (max values) to monitor gain settings, etc.
        stats = [int(np.amax(re_d)), int(np.amax(im_d))]
        if opt.rev_iq:      # reverse spectrum?
            iq_data_cmplx = np.array(im_d + re_d*1j)
        else:               # normal spectrum
            iq_data_cmplx = np.array(re_d + im_d*1j)

    sp_log = myDSP.GetLogPowerSpectrum(iq_data_cmplx)
    if opt.source=='rtl':   # Boost rtl spectrum (arbitrary amount)
        sp_log += 60        # RTL data were normalized to +/- 1.
    
    yscale = float(h_2d)/(sp_max-sp_min)    # yscale is screen units per dB
    # Set the 2d surface to background/graticule.
    surf_2d.blit(surf_2d_graticule, (0, 0))
    
    # Draw the "2d" spectrum graph
    sp_scaled = ((sp_log - sp_min) * yscale) + 3.
    ylist = list(sp_scaled)
    ylist = [ h_2d - x for x in ylist ]                 # flip the y's
    lylist = len(ylist)
    xlist = [ x* w_spectra/lylist for x in range(lylist) ]
    # Draw the spectrum based on our data lists.
    pg.draw.lines(surf_2d, WHITE, False, list(zip(xlist,ylist)), 1)

    # Place 2d spectrum on main surface
    surf_main.blit(pg.transform.rotate(surf_2d,-90), (134, 0))

    if opt.waterfall:
        # Calculate the new Waterfall line and blit it to main surface
        nsum = opt.waterfall_accumulation    # 2d spectra per wf line
        mywf.calculate(sp_log, nsum, surf_wf)
        #surf_main.blit(surf_wf, (x_spectra, y_wf+1))
        surf_main.blit(pg.transform.rotate(surf_wf,-90), (0, 0))

    if info_phase > 0:
        # Assemble and show semi-transparent overlay info screen
        # This takes cpu time, so don't recompute it too often. (DSP & graphics
        # are still running.)
        info_counter = ( info_counter + 1 ) % INFO_CYCLE
        if info_counter == 1:
            # First time through, and every INFO_CYCLE-th time thereafter.
            # Some button labels to show at right of LCD4 window
            # Add labels for LCD4 buttons.
            place_buttons = False
            if opt.lcd4 or (w_main==480):
                place_buttons = True
                button_names = [ " LT", " RT ", " UP", " DN", "ENT" ]
                button_vloc = [ 20, 70, 120, 170, 220 ]
                button_surfs = []
                for bb in button_names:
                    button_surface = medfont.render(bb, 1, WHITE, BLACK)
                    # Rotate button text for landscape orientation
                    button_surface = pg.transform.rotate(button_surface, 270)
                    button_surfs.append(button_surface)

            # Help info will be placed toward top of window.
            # Info comes in 4 phases (0 - 3), cycle among them with <return>
            if info_phase == 1:
                lines = [ "KEYBOARD & TOUCHSCREEN CONTROLS:",
                  "(R) Reset display; (Q) Quit program",
                  "Change upper plot dB limit:  (U) increase; (u) decrease",
                  "Change lower plot dB limit:  (L) increase; (l) decrease",
                  "Change WF palette upper limit: (B) increase; (b) decrease",
                  "Change WF palette lower limit: (D) increase; (d) decrease" ]
                if opt.control != "none":
                    lines.append("Change rcvr freq: (rt arrow) increase; (lt arrow) decrease")
                    lines.append("   Use SHIFT for bigger steps")
                    lines.append("TOUCH: Drag VERTICALLY to change frequency (landscape)")
                    lines.append("   Fine control: small movements, Coarse: large movements")
                    lines.append("   Drag HORIZONTALLY to adjust spectrum dB limits")
                    lines.append("   Tap zones for frequency presets")
                    lines.append("   Double-tap to reset display")
                lines.append("RETURN - Cycle to next Help screen")
            elif info_phase == 2:
                lines = [ "SPECTRUM ADJUSTMENTS (Landscape):",
                          "RIGHT - upper screen level +10 dB",
                          "LEFT - upper screen level -10 dB",
                          "DOWN - lower screen level +10 dB",
                          "UP - lower screen level -10 dB",
                          "RETURN - Cycle to next Help screen" ]
            elif info_phase == 3:
                lines = [ "WATERFALL PALETTE ADJUSTMENTS (Landscape):",
                          "RIGHT - upper threshold INCREASE",
                          "LEFT - upper threshold DECREASE",
                          "DOWN - lower threshold INCREASE",
                          "UP - lower threshold DECREASE",
                          "RETURN - Cycle Help screen OFF" ]
            else:
                lines = [ "Invalid info phase!"]    # we should never arrive here.
                info_phase = 0
            wh = (0, 0)
            for il in lines:                # Find max line width, height
                wh = list(map(max, wh, medfont.size(il)))
            help_matter = pg.Surface((wh[0]+24, len(lines)*wh[1]+15) )
            for ix,x in enumerate(lines):
                help_matter.blit(medfont.render(x, 1, TCOLOR2), (20,ix*wh[1]+15))
            
            # Rotate the help surface for landscape orientation
            help_matter = pg.transform.rotate(help_matter, 270)
            
            # "Live" info is placed toward bottom of window...
            # Width of this surface is a guess. (It should be computed.)
            live_surface = pg.Surface((430,48), 0)
            # give live sp_min, sp_max, v_min, v_max
            msg = "dB scale min= %d, max= %d" % (sp_min, sp_max)
            live_surface.blit(medfont.render(msg, 1, TCOLOR2), (10,0))
            if opt.waterfall:
                # Palette adjustments info
                msg = "WF palette min= %d, max= %d" % (v_min, v_max)
                live_surface.blit(medfont.render(msg, 1, TCOLOR2), (200, 0))
            live_surface.blit(parms_matter, (10,16))
            if opt.source=='audio':
                msg = "ADC max I:%05d; Q:%05d" % (stats[0], stats[1])
                live_surface.blit(medfont.render(msg, 1, TCOLOR2), (10, 32))
            # Show the live cpu load information from cpu_usage thread.
            msg = "Load usr=%3.2f; sys=%3.2f; load avg=%.2f" % \
                (cpu_usage[0], cpu_usage[1], cpu_usage[2])
            live_surface.blit(medfont.render(msg, 1, TCOLOR2), (200, 32))
            
            # Rotate the live surface for landscape orientation
            live_surface = pg.transform.rotate(live_surface, 270)
        # Blit newly formatted -- or old -- screen to main surface.
        if place_buttons:   # Do we have rt hand buttons to place?
            for ix, bb in enumerate(button_surfs):
                surf_main.blit(bb, (449, button_vloc[ix]))
        surf_main.blit(help_matter, (20,20))
        surf_main.blit(live_surface,(20,SCREEN_SIZE[1]-60))
    
    # Draw touch feedback and zones
    draw_touch_zones(surf_main)
    draw_touch_feedback(surf_main)

    # Check for pygame events - keyboard, etc.
    # Note: A key press is not recorded as a PyGame event if you are 
    # connecting via SSH.  In that case, use --sp_min/max and --v_min/max
    # command line options to set scales.

    for event in pg.event.get():
        if event.type == pg.QUIT:
            quit_all()
        elif event.type == pg.FINGERDOWN:
            # Touch started - record initial position and frequency
            touch_active = True
            touch_start_x = event.x * w_main
            touch_start_y = event.y * h_2d
            touch_start_time = time.time()
            print(f"Touch started at ({touch_start_x:.0f}, {touch_start_y:.0f}), control={opt.control}")
            if opt.control == 'rtl':
                touch_start_freq = dataIn.rtl.get_center_freq()
                print(f"RTL start freq: {touch_start_freq/1e6:.3f} MHz")
            elif opt.control == 'si570':
                touch_start_freq = mysi570.getFreqByValue() * 1000
                print(f"Si570 start freq: {touch_start_freq:.3f} kHz")
            elif opt.control == 'hamlib' and 'hamlib_available' in globals() and hamlib_available:
                touch_start_freq = rigfreq
                print(f"Hamlib start freq: {touch_start_freq:.3f} kHz")
            else:
                print(f"No frequency control available")
            
        elif event.type == pg.FINGERUP:
            # Touch ended
            if touch_active:
                # Check if this was a tap (short duration, small movement)
                current_x = event.x * w_main
                current_y = event.y * h_2d
                dx = current_x - touch_start_x
                dy = current_y - touch_start_y
                
                # If movement was small, treat as tap for preset frequencies
                if abs(dx) < 10 and abs(dy) < 10:
                    current_time = time.time()
                    press_duration = current_time - touch_start_time
                    
                                    # Check for long press (help screen)
                    if press_duration > touch_long_press_threshold:
                        # Long press in different zones for different actions
                        if current_y < h_2d / 3:  # Top third - menu navigation
                            handle_touch_menu_navigation(current_x, current_y)
                        elif current_y > 2 * h_2d / 3:  # Bottom third - quick settings
                            handle_touch_quick_settings(current_x, current_y)
                        elif current_y < h_2d / 3:  # Top third - display mode switch
                            handle_touch_display_mode_switch(current_x, current_y)
                        elif current_y < h_2d / 2:  # Upper middle - gain adjustment
                            handle_touch_gain_adjustment(current_x, current_y)
                        elif current_y < 3 * h_2d / 4:  # Lower middle - sample rate adjustment
                            handle_touch_sample_rate_adjustment(current_x, current_y)
                        elif current_y < 7 * h_2d / 8:  # Lower quarter - FFT size adjustment
                            handle_touch_fft_size_adjustment(current_x, current_y)
                        elif current_y < 15 * h_2d / 16:  # Lower eighth - buffer adjustment
                            handle_touch_buffer_adjustment(current_x, current_y)
                        elif current_y < 31 * h_2d / 32:  # Lower sixteenth - waterfall palette adjustment
                            handle_touch_waterfall_palette_adjustment(current_x, current_y)
                        elif current_y < 63 * h_2d / 64:  # Lower thirty-second - waterfall accumulation adjustment
                            handle_touch_waterfall_accumulation_adjustment(current_x, current_y)
                        elif current_y < 127 * h_2d / 128:  # Lower sixty-fourth - pulse clip adjustment
                            handle_touch_pulse_clip_adjustment(current_x, current_y)
                        elif current_y < 255 * h_2d / 256:  # Lower one-hundred-twenty-eighth - skip adjustment
                            handle_touch_skip_adjustment(current_x, current_y)
                        elif current_y < 511 * h_2d / 512:  # Lower two-hundred-fifty-sixth - lagfix adjustment
                            handle_touch_lagfix_adjustment(current_x, current_y)
                        else:  # Bottom five-hundred-twelfth - help screen
                            info_phase = 1
                            info_counter = 0
                            touch_feedback_msg = "Help screen activated"
                            touch_feedback_timer = 60
                            print("Long press - help screen activated")
                    # Check for swipe gesture
                    elif press_duration < 0.5 and (abs(dx) > 50 or abs(dy) > 50):
                        handle_swipe_gesture(touch_start_x, touch_start_y, current_x, current_y, press_duration)
                    # Check for double tap
                    elif current_time - touch_last_tap_time < 0.5:  # Double tap within 0.5 seconds
                        touch_tap_count += 1
                        if touch_tap_count >= 2:  # Double tap detected
                            # Reset display settings
                            sp_min, sp_max = sp_min_def, sp_max_def
                            mygraticule.set_range(sp_min, sp_max)
                            surf_2d_graticule = mygraticule.make()
                            if opt.waterfall:
                                v_min, v_max = mywf.reset_range()
                            touch_feedback_msg = "Display reset"
                            touch_feedback_timer = 60
                            touch_tap_count = 0
                            print("Double tap - display reset")
                    else:
                        touch_tap_count = 1
                        # Check if tap is in frequency step adjustment zone
                        if current_y < h_2d / 6:  # Top sixth - frequency step adjustment
                            handle_touch_frequency_step_adjustment(current_x, current_y)
                        elif current_y < h_2d / 4:  # Top quarter - frequency band switch
                            handle_touch_frequency_band_switch(current_x, current_y)
                        else:  # Regular tap handling
                            handle_touch_tap(current_x, current_y)
                    touch_last_tap_time = current_time
                
                touch_active = False
                print("Touch ended")
                
        elif event.type == pg.FINGERMOTION:
            # Touch movement - adjust frequency based on movement
            if touch_active and (opt.control in ['rtl', 'si570'] or (opt.control == 'hamlib' and 'hamlib_available' in globals() and hamlib_available)):
                current_x = event.x * w_main
                current_y = event.y * h_2d
                dx = current_x - touch_start_x
                dy = current_y - touch_start_y
                
                # Only process if movement is significant
                if abs(dx) > 5 or abs(dy) > 5:
                    print(f"Touch motion: dx={dx:.1f}, dy={dy:.1f}, control={opt.control}")
                    # VERTICAL movement for frequency changes (landscape orientation)
                    if abs(dy) > abs(dx):
                        print(f"Processing frequency change: dy={dy:.1f}")
                        handle_touch_frequency_change(dx, dy, opt.control)
                    # HORIZONTAL movement for dB scale adjustments (landscape orientation)
                    elif abs(dx) > abs(dy):
                        print(f"Processing dB change: dx={dx:.1f}")
                        # Handle spectrum controls
                        handle_spectrum_touch_controls(current_x, current_y, dx, dy)
                        # Handle waterfall controls if enabled
                        if opt.waterfall:
                            handle_waterfall_touch_controls(current_x, current_y, dx, dy)
                    
                    # Update start position for next movement
                    touch_start_x = current_x
                    touch_start_y = current_y
                    
        elif event.type == pg.KEYDOWN:
            if info_phase <= 1:         # Normal op. (0) or help phase 1 (1)
                # We usually want left or right shift treated the same!
                shifted = event.mod & (pg.KMOD_LSHIFT | pg.KMOD_RSHIFT)
                if event.key == pg.K_q:
                    quit_all()
                elif event.key == pg.K_u:            # 'u' or 'U' - chg upper dB (landscape: right/left)
                    if shifted:                         # 'U' move right (increase upper dB)
                        if sp_max < 0:
                            sp_max += 10
                    else:                               # 'u' move left (decrease upper dB)
                        if sp_max > -130 and sp_max > sp_min + 10:
                            sp_max -= 10
                    mygraticule.set_range(sp_min, sp_max)
                    surf_2d_graticule = mygraticule.make()
                elif event.key == pg.K_l:            # 'l' or 'L' - chg lower dB (landscape: down/up)
                    if shifted:                         # 'L' move down (increase lower dB)
                        if sp_min < sp_max -10:
                            sp_min += 10
                    else:                               # 'l' move up (decrease lower dB)
                        if sp_min > -140:
                            sp_min -= 10
                    mygraticule.set_range(sp_min, sp_max)
                    surf_2d_graticule = mygraticule.make()   
                elif event.key == pg.K_b:            # 'b' or 'B' - chg upper pal. (landscape: right/left)
                    if shifted:
                        if v_max < -10:
                            v_max += 10
                    else:
                        if v_max > v_min + 20:
                            v_max -= 10
                    mywf.set_range(v_min,v_max)
                elif event.key == pg.K_d:            # 'd' or 'D' - chg lower pal. (landscape: down/up)
                    if shifted:
                        if v_min < v_max - 20:
                            v_min += 10
                    else:
                        if v_min > -130:
                            v_min -= 10
                    mywf.set_range(v_min,v_max)
                elif event.key == pg.K_r:            # 'r' or 'R' = reset levels
                    sp_min, sp_max = sp_min_def, sp_max_def
                    mygraticule.set_range(sp_min, sp_max)
                    surf_2d_graticule = mygraticule.make()
                    if opt.waterfall:
                        v_min, v_max = mywf.reset_range()

                # Note that LCD peripheral buttons are Right, Left, Up, Down
                # arrows and "Enter".  (Same as keyboard buttons)

                elif event.key == pg.K_RIGHT:        # right arrow + freq
                    if opt.control == 'rtl':
                        finc = 100e3 if shifted else 10e3
                        dataIn.rtl.center_freq = dataIn.rtl.get_center_freq()+finc
                    elif opt.control == 'si570':
                        finc = 1.0 if shifted else 0.1
                        mysi570.setFreqByValue(mysi570.getFreqByValue() + finc*.001)
                    elif opt.hamlib:
                        finc = 1.0 if shifted else 0.1
                        rigfreq_request = rigfreq + finc
                    else:
                        print("Rt arrow ignored, no Hamlib")
                elif event.key == pg.K_LEFT:         # left arrow - freq
                    if opt.control == 'rtl':
                        finc = -100e3 if shifted else -10e3
                        dataIn.rtl.center_freq = dataIn.rtl.get_center_freq()+finc
                    elif opt.control == 'si570':
                        finc = -1.0 if shifted else -0.1
                        mysi570.setFreqByValue(mysi570.getFreqByValue() + finc*.001)
                    elif opt.hamlib:
                        finc = -1.0 if shifted else -0.1
                        rigfreq_request = rigfreq + finc
                    else:
                        print("Lt arrow ignored, no Hamlib")
                elif event.key == pg.K_UP:
                    print("Up")
                elif event.key == pg.K_DOWN:
                    print("Down")
                elif event.key == pg.K_RETURN:
                    info_phase  += 1            # Jump to phase 1 or 2 overlay
                    info_counter = 0            #   (next time)

            # We can have an alternate set of keyboard (LCD button) responses
            # for each "phase" of the on-screen help system.
            
            elif info_phase == 2:               # Listen for info phase 2 keys
                # Showing 2d spectrum gain/offset adjustments (landscape orientation)
                # Note: making graticule is moderately slow.  
                # Do not repeat range changes too quickly!
                if event.key == pg.K_RIGHT:  # Right arrow - increase upper dB (landscape)
                    if sp_max < 0:
                        sp_max += 10
                    mygraticule.set_range(sp_min, sp_max)
                    surf_2d_graticule = mygraticule.make()   
                elif event.key == pg.K_LEFT:  # Left arrow - decrease upper dB (landscape)
                    if sp_max > -130 and sp_max > sp_min + 10:
                        sp_max -= 10
                    mygraticule.set_range(sp_min, sp_max)
                    surf_2d_graticule = mygraticule.make()   
                elif event.key == pg.K_DOWN:  # Down arrow - increase lower dB (landscape)
                    if sp_min < sp_max -10:
                        sp_min += 10
                    mygraticule.set_range(sp_min, sp_max)
                    surf_2d_graticule = mygraticule.make()   
                elif event.key == pg.K_UP:    # Up arrow - decrease lower dB (landscape)
                    if sp_min > -140:
                        sp_min -= 10
                    mygraticule.set_range(sp_min, sp_max)
                    surf_2d_graticule = mygraticule.make()   
                elif event.key == pg.K_RETURN:
                    info_phase = 3 if opt.waterfall \
                            else 0              # Next is phase 3 unless no WF.
                    info_counter = 0

            elif info_phase == 3:               # Listen for info phase 3 keys
                # Showing waterfall palette adjustments (landscape orientation)
                # Note: recalculating palette is quite slow.  
                # Do not repeat range changes too quickly! (1 per second max?)
                if event.key == pg.K_RIGHT:  # Right arrow - increase upper threshold (landscape)
                    if v_max < -10:
                        v_max += 10
                    mywf.set_range(v_min,v_max)
                elif event.key == pg.K_LEFT:  # Left arrow - decrease upper threshold (landscape)
                    if v_max > v_min + 20:
                        v_max -= 10
                    mywf.set_range(v_min,v_max)
                elif event.key == pg.K_DOWN:  # Down arrow - increase lower threshold (landscape)
                    if v_min < v_max - 20:
                        v_min += 10
                    mywf.set_range(v_min,v_max)
                elif event.key == pg.K_UP:    # Up arrow - decrease lower threshold (landscape)
                    if v_min > -130:
                        v_min -= 10
                    mywf.set_range(v_min,v_max)
                elif event.key == pg.K_RETURN:
                    info_phase = 0                  # Turn OFF overlay
                    info_counter = 0

    # Finally, update display for user
    pg.display.update()

    # End of main loop

# END OF IQ.PY

# if this is the main program (not imported), run the main loop
if __name__ == '__main__':
    main()

