import 'dart:async';

import 'package:flutter/material.dart';
import '../models/influencer.dart';
import '../services/voice_service.dart';

class VoiceChatScreen extends StatefulWidget {
  final Influencer influencer;

  const VoiceChatScreen({super.key, required this.influencer});

  @override
  State<VoiceChatScreen> createState() => _VoiceChatScreenState();
}

class _VoiceChatScreenState extends State<VoiceChatScreen>
    with SingleTickerProviderStateMixin {
  final _voiceService = VoiceService();
  final _transcripts = <_TranscriptEntry>[];
  final _scrollController = ScrollController();

  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  StreamSubscription? _stateSub;
  StreamSubscription? _transcriptSub;
  StreamSubscription? _errorSub;

  VoiceState _state = VoiceState.idle;

  @override
  void initState() {
    super.initState();

    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);

    _pulseAnimation = Tween<double>(begin: 0.8, end: 1.2).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    _stateSub = _voiceService.stateStream.listen((state) {
      if (mounted) setState(() => _state = state);
    });

    _transcriptSub = _voiceService.transcriptStream.listen((entry) {
      if (mounted) {
        setState(() {
          _transcripts.add(_TranscriptEntry(
            text: entry.text,
            isAssistant: entry.isAssistant,
          ));
        });
        _scrollToBottom();
      }
    });

    _errorSub = _voiceService.errorStream.listen((message) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(message)),
        );
      }
    });

    _connect();
  }

  Future<void> _connect() async {
    try {
      await _voiceService.connect(
        influencerId: widget.influencer.id,
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Connection failed: $e')),
        );
      }
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    _stateSub?.cancel();
    _transcriptSub?.cancel();
    _errorSub?.cancel();
    _voiceService.disconnect();
    _voiceService.dispose();
    _pulseController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  String get _statusText {
    switch (_state) {
      case VoiceState.idle:
        return 'Disconnected';
      case VoiceState.connecting:
        return 'Connecting...';
      case VoiceState.ready:
        return 'Ready';
      case VoiceState.listening:
        return 'Listening...';
      case VoiceState.thinking:
        return 'Thinking...';
      case VoiceState.speaking:
        return 'Speaking...';
    }
  }

  Color get _statusColor {
    switch (_state) {
      case VoiceState.idle:
        return Colors.grey;
      case VoiceState.connecting:
        return Colors.orange;
      case VoiceState.ready:
        return Colors.blue;
      case VoiceState.listening:
        return Colors.green;
      case VoiceState.thinking:
        return Colors.amber;
      case VoiceState.speaking:
        return Colors.purple;
    }
  }

  bool get _isActive =>
      _state == VoiceState.listening ||
      _state == VoiceState.speaking ||
      _state == VoiceState.thinking;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: Text(widget.influencer.name),
        centerTitle: true,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: Column(
        children: [
          // Persona avatar and status
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 32),
            child: Column(
              children: [
                AnimatedBuilder(
                  animation: _pulseController,
                  builder: (context, child) {
                    final scale = _isActive ? _pulseAnimation.value : 1.0;
                    return Transform.scale(
                      scale: scale,
                      child: Container(
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          boxShadow: _isActive
                              ? [
                                  BoxShadow(
                                    color: _statusColor.withAlpha(100),
                                    blurRadius: 24,
                                    spreadRadius: 8,
                                  ),
                                ]
                              : null,
                        ),
                        child: CircleAvatar(
                          radius: 56,
                          backgroundColor: colorScheme.primaryContainer,
                          backgroundImage:
                              widget.influencer.avatarUrl.isNotEmpty
                                  ? NetworkImage(widget.influencer.avatarUrl)
                                  : null,
                          child: widget.influencer.avatarUrl.isEmpty
                              ? Text(
                                  widget.influencer.initials,
                                  style: TextStyle(
                                    fontSize: 32,
                                    fontWeight: FontWeight.bold,
                                    color: colorScheme.onPrimaryContainer,
                                  ),
                                )
                              : null,
                        ),
                      ),
                    );
                  },
                ),
                const SizedBox(height: 16),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                  decoration: BoxDecoration(
                    color: _statusColor.withAlpha(30),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: _statusColor.withAlpha(80)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: _statusColor,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        _statusText,
                        style: TextStyle(
                          color: _statusColor,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // Transcript list
          Expanded(
            child: _transcripts.isEmpty
                ? Center(
                    child: Text(
                      _state == VoiceState.listening
                          ? 'Start speaking...'
                          : 'Waiting for connection...',
                      style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                            color: colorScheme.onSurfaceVariant,
                          ),
                    ),
                  )
                : ListView.builder(
                    controller: _scrollController,
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    itemCount: _transcripts.length,
                    itemBuilder: (context, index) {
                      final entry = _transcripts[index];
                      return _TranscriptBubble(entry: entry);
                    },
                  ),
          ),

          // Bottom controls
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  // Disconnect button
                  FloatingActionButton.large(
                    heroTag: 'disconnect',
                    backgroundColor: Colors.red.shade700,
                    onPressed: () {
                      _voiceService.disconnect();
                      Navigator.of(context).pop();
                    },
                    child: const Icon(
                      Icons.call_end,
                      color: Colors.white,
                      size: 32,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _TranscriptEntry {
  final String text;
  final bool isAssistant;

  _TranscriptEntry({required this.text, required this.isAssistant});
}

class _TranscriptBubble extends StatelessWidget {
  final _TranscriptEntry entry;

  const _TranscriptBubble({required this.entry});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Align(
        alignment:
            entry.isAssistant ? Alignment.centerLeft : Alignment.centerRight,
        child: Container(
          constraints: BoxConstraints(
            maxWidth: MediaQuery.of(context).size.width * 0.75,
          ),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: entry.isAssistant
                ? colorScheme.secondaryContainer
                : colorScheme.primaryContainer,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Text(
            entry.text,
            style: TextStyle(
              color: entry.isAssistant
                  ? colorScheme.onSecondaryContainer
                  : colorScheme.onPrimaryContainer,
            ),
          ),
        ),
      ),
    );
  }
}
