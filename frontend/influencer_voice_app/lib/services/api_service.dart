import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/influencer.dart';

class ApiService {
  static const String baseUrl = String.fromEnvironment(
    'TAC_API_URL',
    defaultValue: 'https://tac.cytieq.com',
  );

  Future<List<Influencer>> getInfluencers() async {
    final response = await http.get(
      Uri.parse('$baseUrl/api/influencers'),
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to load influencers: ${response.statusCode}');
    }

    final data = json.decode(response.body) as Map<String, dynamic>;
    final list = data['influencers'] as List<dynamic>;

    return list
        .map((json) => Influencer.fromJson(json as Map<String, dynamic>))
        .toList();
  }
}
