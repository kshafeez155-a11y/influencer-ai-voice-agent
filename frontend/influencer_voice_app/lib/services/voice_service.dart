import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:just_audio/just_audio.dart';
import 'package:record/record.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:http/http.dart' as http;
import 'api_service.dart';

enum VoiceState { idle, connecting, ready, listening, thinking, speaking }

class VoiceTranscript {
  final String text;
  final bool isAssistant;
  const VoiceTranscript(this.text, {required this.isAssistant});
}

class VoiceService {
  static const String wsUrl = String.fromEnvironment(
    'TAC_WS_URL',
    defaultValue: 'wss://tac.cytieq.com/ws/voice-chat',
  );

  WebSocketChannel? _channel;
  AudioRecorder? _recorder;
  StreamSubscription? _recorderSubscription;
  StreamSubscription? _wsSubscription;

  final _stateController = StreamController<VoiceState>.broadcast();
  final _transcriptController = StreamController<VoiceTranscript>.broadcast();
  final _errorController = StreamController<String>.broadcast();
  final _bargeInController = StreamController<void>.broadcast();

  Stream<VoiceState> get stateStream => _stateController.stream;
  Stream<VoiceTranscript> get transcriptStream => _transcriptController.stream;
  Stream<String> get errorStream => _errorController.stream;
  Stream<void> get bargeInStream => _bargeInController.stream;

  VoiceState _state = VoiceState.idle;
  VoiceState get state => _state;

  // Audio playback
  final AudioPlayer _player = AudioPlayer();
  final List<int> _pcmBuffer = [];
  Timer? _playbackTimer;
  bool _isPlaying = false;

  void _setState(VoiceState newState) {
    _state = newState;
    _stateController.add(newState);
  }

  Future<void> connect({
    required int influencerId,
    String callerName = '',
  }) async {
    _setState(VoiceState.connecting);

    try {
      final admissionResponse = await http.post(
        Uri.parse('${ApiService.baseUrl}/api/web-call-token'),
        headers: const {'Content-Type': 'application/json'},
        body: json.encode({'influencer_id': influencerId}),
      );
      if (admissionResponse.statusCode != 200) {
        throw StateError('A live call spot could not be reserved.');
      }
      final admission = json.decode(admissionResponse.body) as Map<String, dynamic>;
      final callToken = admission['token'] as String? ?? '';
      if (callToken.isEmpty) throw StateError('The call link was invalid.');
      _channel = WebSocketChannel.connect(Uri.parse(wsUrl));
      await _channel!.ready;

      _wsSubscription = _channel!.stream.listen(
        _handleServerMessage,
        onError: (error) {
          _setState(VoiceState.idle);
        },
        onDone: () {
          _setState(VoiceState.idle);
        },
      );

      // Send start event
      _channel!.sink.add(json.encode({
        'event': 'start',
        'influencer_id': influencerId,
        'caller_name': callerName,
        'call_token': callToken,
      }));
    } catch (e) {
      _setState(VoiceState.idle);
      rethrow;
    }
  }

  void _handleServerMessage(dynamic message) {
    if (message is! String) return;

    final data = json.decode(message) as Map<String, dynamic>;
    final event = data['event'] as String? ?? '';

    switch (event) {
      case 'ready':
        _setState(VoiceState.ready);
        _startRecording();
        break;
      case 'audio':
        _setState(VoiceState.speaking);
        final audioData = data['data'] as String? ?? '';
        if (audioData.isNotEmpty) {
          final bytes = base64Decode(audioData);
          _pcmBuffer.addAll(bytes);
          // Reset the flush timer — play after 300ms of no new chunks
          _playbackTimer?.cancel();
          _playbackTimer = Timer(
            const Duration(milliseconds: 300),
            _flushAudioBuffer,
          );
        }
        break;
      case 'transcript':
        final text = data['text'] as String? ?? '';
        if (text.isNotEmpty) {
          _transcriptController.add(VoiceTranscript(text, isAssistant: true));
        }
        // Transcript arrives after all audio — flush immediately
        _playbackTimer?.cancel();
        _flushAudioBuffer();
        break;
      case 'user_transcript':
        final text = data['text'] as String? ?? '';
        if (text.isNotEmpty) {
          _transcriptController.add(VoiceTranscript(text, isAssistant: false));
        }
        break;
      case 'state':
        if (data['state'] == 'thinking') _setState(VoiceState.thinking);
        break;
      case 'response_done':
        if (!_isPlaying) _setState(VoiceState.listening);
        break;
      case 'error':
        _errorController.add(data['message'] as String? ?? 'The call could not continue.');
        break;
      case 'barge_in':
        _bargeInController.add(null);
        _stopPlayback();
        _setState(VoiceState.listening);
        break;
    }
  }

  /// Convert buffered PCM to WAV and play it.
  Future<void> _flushAudioBuffer() async {
    if (_pcmBuffer.isEmpty) return;

    final pcmBytes = Uint8List.fromList(_pcmBuffer);
    _pcmBuffer.clear();

    final wavBytes = _pcmToWav(pcmBytes, sampleRate: 16000, channels: 1);

    try {
      _isPlaying = true;
      final source = _WavAudioSource(wavBytes);
      await _player.setAudioSource(source);
      await _player.play();
      // Wait for playback to finish
      await _player.playerStateStream.firstWhere(
        (s) => s.processingState == ProcessingState.completed,
      );
    } catch (_) {
      // Player was stopped (barge-in) or errored
    } finally {
      _isPlaying = false;
      if (_state == VoiceState.speaking) {
        _setState(VoiceState.listening);
      }
    }
  }

  void _stopPlayback() {
    _playbackTimer?.cancel();
    _pcmBuffer.clear();
    _player.stop();
    _isPlaying = false;
  }

  /// Build a WAV file from raw PCM s16le data.
  Uint8List _pcmToWav(Uint8List pcmData,
      {required int sampleRate, required int channels}) {
    final dataLen = pcmData.length;
    final byteRate = sampleRate * channels * 2;
    final blockAlign = channels * 2;

    final header = ByteData(44);
    // RIFF
    header.setUint8(0, 0x52); // R
    header.setUint8(1, 0x49); // I
    header.setUint8(2, 0x46); // F
    header.setUint8(3, 0x46); // F
    header.setUint32(4, 36 + dataLen, Endian.little);
    header.setUint8(8, 0x57);  // W
    header.setUint8(9, 0x41);  // A
    header.setUint8(10, 0x56); // V
    header.setUint8(11, 0x45); // E
    // fmt
    header.setUint8(12, 0x66); // f
    header.setUint8(13, 0x6D); // m
    header.setUint8(14, 0x74); // t
    header.setUint8(15, 0x20); // space
    header.setUint32(16, 16, Endian.little); // subchunk size
    header.setUint16(20, 1, Endian.little);  // PCM format
    header.setUint16(22, channels, Endian.little);
    header.setUint32(24, sampleRate, Endian.little);
    header.setUint32(28, byteRate, Endian.little);
    header.setUint16(32, blockAlign, Endian.little);
    header.setUint16(34, 16, Endian.little); // bits per sample
    // data
    header.setUint8(36, 0x64); // d
    header.setUint8(37, 0x61); // a
    header.setUint8(38, 0x74); // t
    header.setUint8(39, 0x61); // a
    header.setUint32(40, dataLen, Endian.little);

    final wav = Uint8List(44 + dataLen);
    wav.setAll(0, header.buffer.asUint8List());
    wav.setAll(44, pcmData);
    return wav;
  }

  Future<void> _startRecording() async {
    _recorder = AudioRecorder();

    final hasPermission = await _recorder!.hasPermission();
    if (!hasPermission) {
      _setState(VoiceState.idle);
      return;
    }

    final stream = await _recorder!.startStream(
      const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: 16000,
        numChannels: 1,
        autoGain: true,
        echoCancel: true,
        noiseSuppress: true,
      ),
    );

    _setState(VoiceState.listening);

    _recorderSubscription = stream.listen((data) {
      if (_channel != null && data.isNotEmpty) {
        final b64 = base64Encode(data);
        _channel!.sink.add(json.encode({
          'event': 'audio',
          'data': b64,
        }));
      }
    });
  }

  Future<void> disconnect() async {
    _stopPlayback();

    await _recorderSubscription?.cancel();
    _recorderSubscription = null;

    if (_recorder != null) {
      try {
        await _recorder!.stop();
      } catch (_) {}
      await _recorder!.dispose();
      _recorder = null;
    }

    if (_channel != null) {
      try {
        _channel!.sink.add(json.encode({'event': 'stop'}));
      } catch (_) {}
      await _channel!.sink.close();
      _channel = null;
    }

    await _wsSubscription?.cancel();
    _wsSubscription = null;

    _setState(VoiceState.idle);
  }

  Future<void> dispose() async {
    await disconnect();
    await _player.dispose();
    _stateController.close();
    _transcriptController.close();
    _errorController.close();
    _bargeInController.close();
  }
}

/// Serves in-memory WAV bytes to just_audio.
class _WavAudioSource extends StreamAudioSource {
  final Uint8List _wavBytes;

  _WavAudioSource(this._wavBytes);

  @override
  Future<StreamAudioResponse> request([int? start, int? end]) async {
    start ??= 0;
    end ??= _wavBytes.length;
    return StreamAudioResponse(
      sourceLength: _wavBytes.length,
      contentLength: end - start,
      offset: start,
      stream: Stream.value(Uint8List.sublistView(_wavBytes, start, end)),
      contentType: 'audio/wav',
    );
  }
}
