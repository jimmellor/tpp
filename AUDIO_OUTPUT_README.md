# Audio Output Functionality for Tiny Python Panadapter

This document describes the enhanced audio output functionality that has been added to the Tiny Python Panadapter (TPP) system, allowing you to actually **hear** the radio signals instead of just seeing them visually.

## What's New

The radio system now includes:
- **Real-time audio output** through speakers/headphones
- **AM and FM demodulation** of I/Q signals
- **Audio device selection** for both input and output
- **Integrated audio processing** with the existing spectrum analyzer

## How It Works

### Before (Visual Only)
- Radio signals → I/Q data → FFT analysis → Spectrum display + Waterfall

### Now (Visual + Audio)
- Radio signals → I/Q data → FFT analysis → Spectrum display + Waterfall
- **AND** I/Q data → Demodulation → Audio output → Speakers/Headphones

## Command Line Options

### Enable Audio Output
```bash
python iq.py --audio_out
```

### Select Demodulation Type
```bash
# Amplitude Modulation (default)
python iq.py --audio_out --demod am

# Frequency Modulation
python iq.py --audio_out --demod fm
```

### Select Audio Output Device
```bash
# Use default output device
python iq.py --audio_out --output_index -1

# Use specific output device (check pa.py for available devices)
python iq.py --audio_out --output_index 2
```

### Complete Example
```bash
# RTL-SDR with AM demodulation and audio output
python iq.py --RTL --audio_out --demod am --WATERFALL

# Audio input with FM demodulation and audio output
python iq.py --audio_out --demod fm --index 0 --WATERFALL
```

## Demodulation Types

### AM (Amplitude Modulation)
- **Best for**: AM radio, SSB, CW signals
- **Method**: `sqrt(I² + Q²)` - extracts amplitude variations
- **Use case**: Traditional AM broadcasting, amateur radio SSB

### FM (Frequency Modulation)
- **Best for**: FM radio, digital signals
- **Method**: Phase derivative - extracts frequency variations
- **Use case**: FM broadcasting, digital modes

## Hardware Requirements

### Input Sources
- **RTL-SDR dongle**: Wideband reception (±1.024 MHz)
- **Audio sound card**: Traditional radio IF output (±48 kHz)
- **Si570 DDS**: Frequency control (SoftRock-style radios)

### Output
- **Speakers or headphones** connected to your computer
- **Audio output device** (built-in sound card, USB audio, etc.)

## Testing the Audio Output

### 1. Quick Test
```bash
python test_audio_output.py
```
This will play test tones to verify your audio output is working.

### 2. Real Radio Test
```bash
# Connect RTL-SDR and enable audio output
python iq.py --RTL --audio_out --demod am --WATERFALL

# Or use audio input from a real radio
python iq.py --audio_out --demod fm --index 0 --WATERFALL
```

## Troubleshooting

### No Audio Output
1. **Check volume**: Ensure system volume is up and not muted
2. **Check device**: Run `pa.py` to see available output devices
3. **Check permissions**: Ensure you have audio access
4. **Check connections**: Verify speakers/headphones are connected

### Audio Quality Issues
1. **Sample rate**: Try different sample rates (48000 Hz recommended)
2. **Buffer size**: Adjust `--size` parameter for better performance
3. **Demodulation**: Try switching between AM and FM
4. **Filtering**: The system includes automatic low-pass filtering

### Performance Issues
1. **Reduce FFT size**: Use smaller `--size` values
2. **Reduce buffers**: Use fewer `--n_buffers`
3. **Skip frames**: Use `--skip` parameter to reduce CPU load

## Advanced Usage

### Custom Audio Processing
You can modify the `play_demodulated_audio()` method in `iq_af.py` to add:
- Custom filters
- Noise reduction
- Audio effects
- Different demodulation algorithms

### Multiple Output Streams
The system can be extended to support:
- Multiple audio outputs
- Recording to files
- Network audio streaming
- Audio level meters

## Technical Details

### Audio Format
- **Sample rate**: Configurable (default: 48 kHz)
- **Bit depth**: 16-bit signed integer
- **Channels**: Stereo (2 channels)
- **Buffer size**: Configurable for latency vs. performance

### Demodulation Process
1. **I/Q extraction**: Separate I and Q components
2. **Signal processing**: Apply demodulation algorithm
3. **Filtering**: Low-pass filter to reduce noise
4. **Normalization**: Scale to appropriate audio levels
5. **Output**: Send to audio device

### Performance Considerations
- **Latency**: Smaller buffers = lower latency but higher CPU usage
- **Quality**: Larger FFT sizes = better frequency resolution
- **Real-time**: System designed for real-time operation

## Examples

### Listening to FM Radio
```bash
# Tune to FM station and listen
python iq.py --RTL --rtl_freq 100.1e6 --audio_out --demod fm
```

### Listening to Amateur Radio
```bash
# Listen to SSB signals
python iq.py --RTL --rtl_freq 7.074e6 --audio_out --demod am
```

### Audio Input from Real Radio
```bash
# Connect radio's IF output to sound card
python iq.py --audio_out --demod am --index 0
```

## Future Enhancements

Potential improvements could include:
- **SSB demodulation** for amateur radio
- **CW decoding** for Morse code
- **Digital mode decoding** (PSK31, RTTY, etc.)
- **Audio recording** to files
- **Multiple audio outputs** for different demodulation types
- **Audio level meters** and VU displays

## Support

If you encounter issues:
1. Check this README for troubleshooting steps
2. Run the test script to verify basic functionality
3. Check system audio settings and permissions
4. Verify hardware connections and compatibility

## License

This enhancement maintains the same GPL v3 license as the original TPP project.

---

**Enjoy listening to your radio signals!** 🎵📻
