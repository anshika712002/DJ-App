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

  group('parseRole', () {
    test('parses backend roles', () {
      expect(parseRole('dj'), UserRole.dj);
      expect(parseRole('user'), UserRole.user);
      expect(parseRole('admin'), UserRole.user);
    });
  });

  group('Song.fromJson', () {
    test('accepts Audius-style and fallback id keys', () {
      expect(Song.fromJson({'videoId': 'abc'}).videoId, 'abc');
      expect(Song.fromJson({'trackId': 'def'}).videoId, 'def');
      expect(Song.fromJson({'id': 'ghi'}).videoId, 'ghi');
    });

    test('maps search result fields', () {
      final song = Song.fromJson({
        'videoId': 'abc',
        'title': 'Nightcall',
        'artistName': 'Kavinsky',
        'thumbnail': 'https://example.com/art.jpg',
        'duration': 258,
        'genre': 'synthwave',
      });
      expect(song.title, 'Nightcall');
      expect(song.artistName, 'Kavinsky');
      expect(song.duration, 258);
      expect(song.genre, 'synthwave');
      expect(song.downloadAble, isTrue);
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
          {'videoId': 'a', 'title': 'Nightcall'},
          {'videoId': 'b', 'title': 'Sunrise'},
        ],
        'restaurantName': 'Cafe Wave',
      });

      expect(item.id, 12);
      expect(item.status, 'accepted');
      expect(item.mixedAudioUrl, '/requests/audio/mix_abc_overlay.mp3');
      expect(item.tipAmount, 5.5);
      expect(item.mixerType, 'crossfade');
      expect(item.requestedBy, 'anshika');
      expect(item.restaurantName, 'Cafe Wave');
      expect(item.songs, hasLength(2));
      expect(item.songs.first.videoId, 'a');
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
        'restaurantName': null,
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
      role: 'dj',
    );

    test('derives the user role', () {
      expect(session.userRole, UserRole.dj);
    });

    test('copyWith only replaces the given tokens', () {
      final updated = session.copyWith(accessToken: 'a2');
      expect(updated.accessToken, 'a2');
      expect(updated.refreshToken, 'r1');
      expect(updated.userName, 'anshika');
      expect(updated.role, 'dj');
    });

    test('round-trips through JSON', () {
      final parsed = AuthSession.fromJson(session.toJson());
      expect(parsed.accessToken, 'a1');
      expect(parsed.role, 'dj');
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
