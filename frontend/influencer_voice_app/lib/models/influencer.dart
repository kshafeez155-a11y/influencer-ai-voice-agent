class Influencer {
  final int id;
  final String name;
  final String tagline;
  final String bio;
  final String avatarUrl;
  final String voiceId;
  final String primaryLanguage;
  final List<String> supportedLanguages;
  final int maxCallSeconds;

  const Influencer({
    required this.id,
    required this.name,
    required this.tagline,
    required this.bio,
    required this.avatarUrl,
    required this.voiceId,
    required this.primaryLanguage,
    required this.supportedLanguages,
    required this.maxCallSeconds,
  });

  factory Influencer.fromJson(Map<String, dynamic> json) {
    return Influencer(
      id: json['id'] as int,
      name: json['name'] as String? ?? '',
      tagline: json['tagline'] as String? ?? '',
      bio: json['bio'] as String? ?? '',
      avatarUrl: json['avatar_url'] as String? ?? '',
      voiceId: json['voice_id'] as String? ?? '',
      primaryLanguage: json['primary_language'] as String? ?? 'en',
      supportedLanguages: (json['supported_languages'] as List<dynamic>? ?? const ['en'])
          .map((value) => value.toString())
          .toList(),
      maxCallSeconds: json['max_call_seconds'] as int? ?? 300,
    );
  }

  String get initials {
    final parts = name.split(' ');
    if (parts.length >= 2) {
      return '${parts[0][0]}${parts[1][0]}'.toUpperCase();
    }
    return name.isNotEmpty ? name[0].toUpperCase() : '?';
  }
}
