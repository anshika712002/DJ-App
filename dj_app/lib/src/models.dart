enum UserRole { user, dj }

UserRole parseRole(String value) =>
    UserRole.values.firstWhere((r) => r.name == value, orElse: () => UserRole.user);

const Set<String> kRequestStatuses = {
  'pending',
  'accepted',
  'rejected',
  'playing',
  'played',
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
  final String role;
  final String? phone;
  final String? email;
  final String? restaurantName;

  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.userName,
    required this.role,
    this.phone,
    this.email,
    this.restaurantName,
  });

  factory AuthSession.fromJson(Map<String, dynamic> json) => AuthSession(
        accessToken: json['accessToken'] as String,
        refreshToken: json['refreshToken'] as String? ?? '',
        userName: json['userName'] as String? ?? '',
        role: json['role'] as String? ?? 'user',
        phone: json['phone'] as String?,
        email: json['email'] as String?,
        restaurantName: json['restaurantName'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'accessToken': accessToken,
        'refreshToken': refreshToken,
        'userName': userName,
        'role': role,
        'phone': phone,
        'email': email,
        'restaurantName': restaurantName,
      };

  AuthSession copyWith({String? accessToken, String? refreshToken}) => AuthSession(
        accessToken: accessToken ?? this.accessToken,
        refreshToken: refreshToken ?? this.refreshToken,
        userName: userName,
        role: role,
        phone: phone,
        email: email,
        restaurantName: restaurantName,
      );

  UserRole get userRole => parseRole(role);
}

class Song {
  final String videoId;
  final String? title;
  final String? artistName;
  final String? thumbnail;
  final int? duration;
  final String? genre;
  final bool downloadAble;

  const Song({
    required this.videoId,
    this.title,
    this.artistName,
    this.thumbnail,
    this.duration,
    this.genre,
    this.downloadAble = true,
  });

  factory Song.fromJson(Map<String, dynamic> json) => Song(
        videoId: (json['videoId'] ?? json['trackId'] ?? json['id']) as String,
        title: json['title'] as String?,
        artistName: (json['artistName'] ?? json['artist']) as String?,
        thumbnail: (json['thumbnail'] ?? json['artwork']) as String?,
        duration: (json['duration'] as num?)?.toInt(),
        genre: json['genre'] as String?,
        downloadAble: json['downloadAble'] as bool? ?? true,
      );
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
  final String? restaurantName;

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
    required this.restaurantName,
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
        restaurantName: json['restaurantName'] as String?,
      );
}

const List<String> kMixers = [
  'overlay',
  'alternate',
  'crossfade',
  'tempo-sync',
  'pitch-shift',
  'beat-overlay',
  'without-mixing',
];

