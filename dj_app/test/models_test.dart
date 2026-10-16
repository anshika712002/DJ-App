import 'package:flutter_test/flutter_test.dart';

import 'package:dj_app/src/models.dart';

void main() {
  group('statusLabel', () {
    test('capitalises the first letter', () {
      expect(statusLabel('pending'), 'Pending');
      expect(statusLabel('played'), 'Played');
      expect(statusLabel(''), 'unknown');
    });

    test('every known status maps to a colour', () {
      for (final status in kRequestStatuses) {
        expect(statusLabel(status), isNotEmpty);
      }
    });
  });

  group('Song.fromJson', () {
    test('accepts legacy and fallback ID keys', () {
      expect(Song.fromJson({'videoId': 'abc'}).trackId, 'abc');
      expect(Song.fromJson({'trackId': 'def'}).trackId, 'def');
      expect(Song.fromJson({'id': 'ghi'}).trackId, 'ghi');
    });

    test('maps the shared source-aware track contract', () {
      final song = Song.fromJson({
        'trackId': 'abc',
        'sourceType': 'youtube',
        'title': 'Nightcall',
        'artist': 'Kavinsky',
        'artwork': 'https://example.com/art.jpg',
        'duration': 258,
        'playbackUrl': 'https://www.youtube.com/watch?v=abc',
        'mixEligible': false,
        'license': 'YouTube',
        'attribution': 'Kavinsky',
      });
      expect(song.title, 'Nightcall');
      expect(song.artist, 'Kavinsky');
      expect(song.sourceType, 'youtube');
      expect(song.artwork, 'https://example.com/art.jpg');
      expect(song.duration, 258);
      expect(song.playbackUrl, 'https://www.youtube.com/watch?v=abc');
      expect(song.mixEligible, isFalse);
      expect(song.license, 'YouTube');
      expect(song.attribution, 'Kavinsky');
    });

    test('maps a mixable local asset', () {
      final song = Song.fromJson({
        'trackId': 'asset:9',
        'sourceType': 'licensed',
        'title': 'Licensed loop',
        'mixEligible': true,
        'license': 'CC BY 4.0',
        'attribution': 'Artist',
      });
      expect(song.trackId, 'asset:9');
      expect(song.sourceType, 'licensed');
      expect(song.mixEligible, isTrue);
      expect(song.license, 'CC BY 4.0');
    });
  });

  group('RequestItem.fromJson', () {
    test('parses the /requests/allSongs payload', () {
      final item = RequestItem.fromJson({
        'songRequestId': 12,
        'songStatus': 'accepted',
        'mixedAudioUrl': '/requests/audio/mix_abc_overlay.mp3',
        'tipAmount': 5.5,
        'mixSongTitle': 'Nightcall + Sunrise',
        'mixerType': 'crossfade',
        'requestedBy': 'anshika',
        'requestedAt': '2026-10-08T10:00:00Z',
        'playedAt': null,
        'requestedSongs': [
          {'trackId': 'a', 'sourceType': 'youtube', 'title': 'Nightcall'},
          {'trackId': 'b', 'sourceType': 'youtube', 'title': 'Sunrise'},
        ],
      });

      expect(item.id, 12);
      expect(item.status, 'accepted');
      expect(item.mixedAudioUrl, '/requests/audio/mix_abc_overlay.mp3');
      expect(item.tipAmount, 5.5);
      expect(item.mixerType, 'crossfade');
      expect(item.requestedBy, 'anshika');
      expect(item.songs, hasLength(2));
      expect(item.songs.first.trackId, 'a');
      expect(item.playedAt, isNull);
    });

    test('tolerates missing optional fields', () {
      final item = RequestItem.fromJson({
        'songRequestId': 1,
        'songStatus': 'pending',
        'mixedAudioUrl': null,
        'tipAmount': 0,
        'mixSongTitle': null,
        'mixerType': null,
        'requestedBy': null,
        'requestedAt': null,
        'playedAt': null,
        'requestedSongs': null,
      });
      expect(item.status, 'pending');
      expect(item.mixSongTitle, '');
      expect(item.mixerType, 'overlay');
      expect(item.songs, isEmpty);
    });
  });

  group('AuthSession', () {
    const session = AuthSession(
      accessToken: 'a1',
      refreshToken: 'r1',
      userName: 'anshika',
    );

    test('copyWith only replaces the given tokens', () {
      final updated = session.copyWith(accessToken: 'a2');
      expect(updated.accessToken, 'a2');
      expect(updated.refreshToken, 'r1');
      expect(updated.userName, 'anshika');
    });

    test('round-trips through JSON', () {
      final parsed = AuthSession.fromJson(session.toJson());
      expect(parsed.accessToken, 'a1');
      expect(parsed.refreshToken, 'r1');
      expect(parsed.userName, 'anshika');
    });
  });

  group('ApiResponse', () {
    test('reads the app envelope', () {
      final response = ApiResponse.fromJson({
        'statusCode': 200,
        'status': 'Login successful',
        'data': {'accessToken': 'abc'},
      });
      expect(response.statusCode, 200);
      expect(response.status, 'Login successful');
      expect(response.isSuccess, isTrue);
      expect((response.data as Map)['accessToken'], 'abc');
    });
  });
}
