import 'config.dart';
import 'api_client.dart';
import 'models.dart';

/// Endpoint wrappers for the song-request surface of the backend.
class SongApi {
  SongApi(this._api);

  final ApiClient _api;

  Future<List<Song>> search(String query) async {
    final raw = await _api.get('/requests/searchSong', query: {'q': query});
    final results = _map(raw)?['results'];
    return (results as List<dynamic>? ?? [])
        .map((e) => Song.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<Song>> suggested() async {
    final raw = await _api.get('/requests/suggestedSongs');
    final results = _map(raw)?['results'];
    return (results as List<dynamic>? ?? [])
        .map((e) => Song.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Genuine recent searches for the authenticated user (newest first). Used
  /// only for the clearly-labelled history section, never as fresh results.
  Future<List<String>> searchHistory() async {
    final raw = await _api.get('/requests/searchHistory');
    final queries = _map(raw)?['queries'];
    return (queries as List<dynamic>? ?? [])
        .whereType<String>()
        .toList(growable: false);
  }

  Future<List<Song>> searchAssets(String query) async {
    final raw = await _api.get('/tracks/assets', query: {'q': query});
    return (raw as List<dynamic>? ?? [])
        .map((e) => Song.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<int> requestMix({
    required List<Song> tracks,
    double? tipAmount,
    String? mixer,
  }) async {
    final body = <String, dynamic>{
      'tracks': tracks
          .map((track) => {
                'trackId': track.trackId,
                'sourceType': track.sourceType,
              })
          .toList(),
    };
    if (tipAmount != null) body['tipAmount'] = tipAmount;
    if (mixer != null) body['mixer'] = mixer;
    final raw = await _api.post('/requests/requestSong', body: body);
    final requestId = _map(raw)?['requestId'];
    if (requestId is! num) {
      throw const ApiException(500, 'Server did not return a request id');
    }
    return requestId.toInt();
  }

  /// The authenticated user's own requests (the backend scopes this to the
  /// caller). Newest first.
  Future<List<RequestItem>> all() async {
    final raw = await _api.get('/requests/allSongs');
    final data = _map(raw)?['data'];
    return (data as List<dynamic>? ?? [])
        .map((e) => RequestItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// The backend accepts the token as a query parameter so media players that
  /// cannot send an Authorization header can still stream the file.
  String? audioUrl(RequestItem item) {
    final path = item.mixedAudioUrl;
    if (path == null || path.isEmpty) return null;
    final token = _api.accessToken;
    if (token == null || token.isEmpty) return null;
    final uri = path.startsWith('http')
        ? Uri.parse(path)
        : Uri.parse(AppConfig.httpUrl(path));
    return uri.replace(queryParameters: {...uri.queryParameters, 'token': token}).toString();
  }

  String? playbackUrl(Song track) {
    final path = track.playbackUrl;
    if (path == null || path.isEmpty) return null;
    final uri = path.startsWith('http')
        ? Uri.parse(path)
        : Uri.parse(AppConfig.httpUrl(path));
    if (track.sourceType == 'youtube') return uri.toString();
    final token = _api.accessToken;
    if (token == null || token.isEmpty) return null;
    return uri.replace(queryParameters: {...uri.queryParameters, 'token': token}).toString();
  }

  static Map<String, dynamic>? _map(dynamic value) =>
      value is Map<String, dynamic> ? value : null;
}
