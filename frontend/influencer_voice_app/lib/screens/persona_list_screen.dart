import 'package:flutter/material.dart';
import '../models/influencer.dart';
import '../services/api_service.dart';
import 'voice_chat_screen.dart';

class PersonaListScreen extends StatefulWidget {
  const PersonaListScreen({super.key});

  @override
  State<PersonaListScreen> createState() => _PersonaListScreenState();
}

class _PersonaListScreenState extends State<PersonaListScreen> {
  final _apiService = ApiService();
  late Future<List<Influencer>> _influencersFuture;

  @override
  void initState() {
    super.initState();
    _influencersFuture = _apiService.getInfluencers();
  }

  void _refresh() {
    setState(() {
      _influencersFuture = _apiService.getInfluencers();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Voice Chat'),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _refresh,
          ),
        ],
      ),
      body: FutureBuilder<List<Influencer>>(
        future: _influencersFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }

          if (snapshot.hasError) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline, size: 48),
                  const SizedBox(height: 16),
                  Text(
                    'Could not load personas',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    snapshot.error.toString(),
                    style: Theme.of(context).textTheme.bodySmall,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 16),
                  FilledButton.tonal(
                    onPressed: _refresh,
                    child: const Text('Retry'),
                  ),
                ],
              ),
            );
          }

          final influencers = snapshot.data ?? [];

          if (influencers.isEmpty) {
            return const Center(
              child: Text('No personas available'),
            );
          }

          return GridView.builder(
            padding: const EdgeInsets.all(16),
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              childAspectRatio: 0.75,
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
            ),
            itemCount: influencers.length,
            itemBuilder: (context, index) {
              return _PersonaCard(
                influencer: influencers[index],
                onTap: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => VoiceChatScreen(
                        influencer: influencers[index],
                      ),
                    ),
                  );
                },
              );
            },
          );
        },
      ),
    );
  }
}

class _PersonaCard extends StatelessWidget {
  final Influencer influencer;
  final VoidCallback onTap;

  const _PersonaCard({
    required this.influencer,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              CircleAvatar(
                radius: 36,
                backgroundColor: colorScheme.primaryContainer,
                backgroundImage: influencer.avatarUrl.isNotEmpty
                    ? NetworkImage(influencer.avatarUrl)
                    : null,
                child: influencer.avatarUrl.isEmpty
                    ? Text(
                        influencer.initials,
                        style: TextStyle(
                          fontSize: 24,
                          fontWeight: FontWeight.bold,
                          color: colorScheme.onPrimaryContainer,
                        ),
                      )
                    : null,
              ),
              const SizedBox(height: 12),
              Text(
                influencer.name,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                textAlign: TextAlign.center,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 4),
              Text(
                influencer.tagline,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: colorScheme.onSurfaceVariant,
                    ),
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
