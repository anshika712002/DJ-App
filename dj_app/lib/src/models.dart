const Set<String> kRequestStatuses = {
  'pending',
  'accepted',
  'rejected',
  'playing',
  'played',
  'ready',
  'completed',
  'failed',
};

String statusLabel(String status) {
  if (status.isEmpty) return 'unknown';
  return status[0].toUpperCase() + status.substring(1);
}

/// Auth envelope returned by /auth/* and /user/* endpoints.
class ApiResponse {
  final int? statusCode;
  final String? status;
  final dynamic data;

  const ApiResponse({this.statusCode, this.status, this.data});

  factory ApiResponse.fromJson(Map<String, dynamic> json) => ApiResponse(
        statusCode: json['statusCode'] as int?,
        status: json['status'] as String?,
        data: json['data'],
      );

  bool get isSuccess => statusCode == null || statusCode == 200;
}

class AuthSession {
  final String accessToken;
  final String refreshToken;
  final String userName;
  final String? phone;
  final String? email;

  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.userName,
    this.phone,
    this.email,
  });

  factory AuthSession.fromJson(Map<String, dynamic> json) => AuthSession(
        accessToken: json['accessToken'] as String,
        refreshToken: json['refreshToken'] as String? ?? '',
        userName: json['userName'] as String? ?? '',
        phone: json['phone'] as String?,
        email: json['email'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'accessToken': accessToken,
        'refreshToken': refreshToken,
        'userName': userName,
        'phone': phone,
        'email': email,
      };

  AuthSession copyWith({String? accessToken, String? refreshToken}) => AuthSession(
        accessToken: accessToken ?? this.accessToken,
        refreshToken: refreshToken ?? this.refreshToken,
        userName: userName,
        phone: phone,
        email: email,
      );
}

class Song {
  final String trackId;
  final String sourceType;
  final String? title;
  final String? artist;
  final String? artwork;
  final int? duration;
  final String? playbackUrl;
  final bool mixEligible;
  final String? license;
  final String? attribution;

  const Song({
    required this.trackId,
    this.sourceType = 'youtube',
    this.title,
    this.artist,
    this.artwork,
    this.duration,
    this.playbackUrl,
    this.mixEligible = false,
    this.license,
    this.attribution,
  });

  factory Song.fromJson(Map<String, dynamic> json) => Song(
        trackId: (json['trackId'] ?? json['videoId'] ?? json['id']) as String,
        sourceType: json['sourceType'] as String? ?? 'youtube',
        title: json['title'] as String?,
        artist: (json['artist'] ?? json['artistName']) as String?,
        artwork: (json['artwork'] ?? json['thumbnail']) as String?,
        duration: (json['duration'] as num?)?.toInt(),
        playbackUrl: json['playbackUrl'] as String?,
        mixEligible: json['mixEligible'] as bool? ?? json['downloadAble'] as bool? ?? false,
        license: json['license'] as String?,
        attribution: json['attribution'] as String?,
      );

  /// A track is uniquely identified by its source + id, so selection and
  /// de-duplication behave predictably across re-renders and refreshes.
  @override
  bool operator ==(Object other) =>
      other is Song && other.trackId == trackId && other.sourceType == sourceType;

  @override
  int get hashCode => Object.hash(trackId, sourceType);
}

class RequestItem {
  final int id;
  final String status;
  final String? mixedAudioUrl;
  final double tipAmount;
  final String mixSongTitle;
  final String mixerType;
  final String requestedBy;
  final String requestedAt;
  final String? playedAt;
  final List<Song> songs;

  const RequestItem({
    required this.id,
    required this.status,
    required this.mixedAudioUrl,
    required this.tipAmount,
    required this.mixSongTitle,
    required this.mixerType,
    required this.requestedBy,
    required this.requestedAt,
    required this.playedAt,
    required this.songs,
  });

  factory RequestItem.fromJson(Map<String, dynamic> json) => RequestItem(
        id: (json['songRequestId'] as num).toInt(),
        status: json['songStatus'] as String? ?? 'pending',
        mixedAudioUrl: json['mixedAudioUrl'] as String?,
        tipAmount: (json['tipAmount'] as num?)?.toDouble() ?? 0,
        mixSongTitle: json['mixSongTitle'] as String? ?? '',
        mixerType: json['mixerType'] as String? ?? 'overlay',
        requestedBy: json['requestedBy'] as String? ?? 'Unknown',
        requestedAt: json['requestedAt'] as String? ?? '',
        playedAt: json['playedAt'] as String?,
        songs: (json['requestedSongs'] as List<dynamic>? ?? [])
            .map((s) => Song.fromJson(s as Map<String, dynamic>))
            .toList(),
      );
}

const List<String> kMixers = [
  'overlay',
  'alternate',
  'crossfade',
  'tempo-sync',
  'pitch-shift',
  'beat-overlay',
  'beat-background',
  'without-mixing',
];
