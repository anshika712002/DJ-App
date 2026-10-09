import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:dj_app/src/api_client.dart';
import 'package:dj_app/src/models.dart';
import 'package:dj_app/src/song_api.dart';

void main() {
  test('requestMix submits source-aware track references', () async {
    late Map<String, dynamic> posted;
    final client = ApiClient(
      httpClient: MockClient((request) async {
        posted = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(jsonEncode({'requestId': 23}), 200);
      }),
    );
    final api = SongApi(client);

    final requestId = await api.requestMix(
      tracks: const [
        Song(
          trackId: 'asset:5',
          sourceType: 'licensed',
          title: 'Licensed loop',
          mixEligible: true,
        ),
      ],
      mixer: 'crossfade',
    );

    expect(requestId, 23);
    expect(posted['tracks'], [
      {'trackId': 'asset:5', 'sourceType': 'licensed'},
    ]);
    expect(posted.containsKey('trackIds'), isFalse);
  });
}
