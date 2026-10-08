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

  Future<int> requestMix({
    required List<String> trackIds,
    double? tipAmount,
    String? mixer,
  }) async {
    final body = <String, dynamic>{'trackIds': trackIds};
    if (tipAmount != null) body['tipAmount'] = tipAmount;
    if (mixer != null) body['mixer'] = mixer;
    final raw = await _api.post('/requests/requestSong', body: body);
    final requestId = _map(raw)?['requestId'];
    if (requestId is! num) {
      throw const ApiException(500, 'Server did not return a request id');
    }
    return requestId.toInt();
  }

  Future<List<RequestItem>> all({bool mineOnly = false, String? status}) async {
    final query = <String, String>{'mineOnly': mineOnly.toString()};
    if (status != null) query['status'] = status;
    final raw = await _api.get('/requests/allSongs', query: query);
    final data = _map(raw)?['data'];
    return (data as List<dynamic>? ?? [])
        .map((e) => RequestItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> accept(int id) => _api.put('/requests/accept/$id');

  Future<void> reject(int id) => _api.put('/requests/reject/$id');

  Future<void> updateStatus(int id, String status) =>
      _api.put('/requests/updateStatus/$id', body: {'status': status});

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

  static Map<String, dynamic>? _map(dynamic value) =>
      value is Map<String, dynamic> ? value : null;
}
