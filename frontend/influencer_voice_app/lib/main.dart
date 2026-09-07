import 'package:flutter/material.dart';
import 'screens/persona_list_screen.dart';

void main() {
  runApp(const InfluencerVoiceApp());
}

class InfluencerVoiceApp extends StatelessWidget {
  const InfluencerVoiceApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TAC Voice',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFFF3D63),
          brightness: Brightness.light,
          surface: const Color(0xFFF7F8FA),
        ),
        useMaterial3: true,
      ),
      home: const PersonaListScreen(),
    );
  }
}
