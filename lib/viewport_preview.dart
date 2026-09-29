import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'app_language.dart';

/// Polls the newest viewport frame independently of the camera control socket.
class ViewportPreview extends StatefulWidget {
  const ViewportPreview({
    super.key,
    required this.connected,
    required this.host,
    required this.port,
    required this.token,
    required this.width,
    this.expanded = false,
    this.fullscreen = false,
  });

  final bool connected;
  final String host;
  final int port;
  final String token;
  final int width;
  final bool expanded;
  final bool fullscreen;

  @override
  State<ViewportPreview> createState() => _ViewportPreviewState();
}

class _ViewportPreviewState extends State<ViewportPreview> {
  String _translateBlenderError(String message) {
    if (message == 'Select a camera in Blender') {
      return uiText('Seleziona una camera in Blender', message);
    }
    if (message == 'Open a 3D View in Blender') {
      return uiText('Apri una Vista 3D in Blender', message);
    }
    return uiText('Anteprima non disponibile; controlla Blender', message);
  }

  HttpClient? _client;
  Uint8List? _frame;
  String _message = uiText(
    'Connetti Blender per vedere la scena',
    'Connect to Blender to see the scene',
  );
  double _aspect = 16 / 9;
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    _start();
  }

  @override
  void didUpdateWidget(covariant ViewportPreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.connected != widget.connected ||
        oldWidget.host != widget.host ||
        oldWidget.port != widget.port ||
        oldWidget.token != widget.token ||
        oldWidget.width != widget.width) {
      _start();
    }
  }

  @override
  void dispose() {
    _generation++;
    _client?.close(force: true);
    super.dispose();
  }

  void _start() {
    _generation++;
    _client?.close(force: true);
    _frame = null;
    _message = widget.connected && widget.port == 0
        ? uiText(
            'Aggiorna l’add-on Blender per attivare l’anteprima',
            'Update the Blender add-on to enable the preview',
          )
        : widget.connected
        ? uiText(
            'Attendo la vista della camera…',
            'Waiting for the camera view…',
          )
        : uiText(
            'Connetti Blender per vedere la scena',
            'Connect to Blender to see the scene',
          );
    if (widget.connected && widget.port > 0 && widget.host.isNotEmpty) {
      _client = HttpClient()..connectionTimeout = const Duration(seconds: 3);
      unawaited(_poll(_generation, _client!));
    } else {
      _client = null;
    }
  }

  Future<void> _poll(int generation, HttpClient client) async {
    var sequence = 0;
    while (mounted && generation == _generation) {
      try {
        final url = Uri(
          scheme: 'http',
          host: widget.host,
          port: widget.port,
          path: '/frame',
          queryParameters: {'since': '$sequence', 'width': '${widget.width}'},
        );
        final request = await client.getUrl(url);
        request.headers.set('X-Action2Blender-Token', widget.token);
        final response = await request.close().timeout(
          const Duration(seconds: 5),
        );
        if (response.statusCode == HttpStatus.noContent) {
          await response.drain<void>();
          continue;
        }
        final bytes = BytesBuilder(copy: false);
        await for (final chunk in response.timeout(
          const Duration(seconds: 5),
        )) {
          bytes.add(chunk);
          if (bytes.length > 4 * 1024 * 1024) {
            throw FormatException(
              uiText('Fotogramma troppo grande', 'Frame too large'),
            );
          }
        }
        if (!mounted || generation != _generation) return;
        if (response.statusCode != HttpStatus.ok) {
          final error = String.fromCharCodes(bytes.takeBytes());
          setState(
            () => _message = error.isEmpty
                ? uiText('Anteprima non disponibile', 'Preview unavailable')
                : _translateBlenderError(error),
          );
          await Future<void>.delayed(const Duration(seconds: 1));
          continue;
        }
        final frame = bytes.takeBytes();
        if (frame.length < 24) {
          throw FormatException(
            uiText('Fotogramma non valido', 'Invalid frame'),
          );
        }
        final dimensions = ByteData.sublistView(frame);
        final width = dimensions.getUint32(16);
        final height = dimensions.getUint32(20);
        if (width == 0 || height == 0) {
          throw FormatException(
            uiText('Dimensioni non valide', 'Invalid dimensions'),
          );
        }
        sequence =
            int.tryParse(response.headers.value('X-Frame-Seq') ?? '') ??
            sequence;
        setState(() {
          _frame = frame;
          _aspect = width / height;
          _message = '';
        });
      } catch (_) {
        if (!mounted || generation != _generation) return;
        setState(
          () => _message = uiText(
            'Segnale video interrotto: riconnessione…',
            'Video interrupted: reconnecting…',
          ),
        );
        await Future<void>.delayed(const Duration(seconds: 1));
      }
    }
  }

  Widget _picture() => ColoredBox(
    color: Colors.black,
    child: Stack(
      fit: StackFit.expand,
      children: [
        if (_frame != null)
          Image.memory(_frame!, fit: BoxFit.contain, gaplessPlayback: true),
        if (_message.isNotEmpty)
          Center(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Text(_message, textAlign: TextAlign.center),
            ),
          ),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) {
    if (widget.fullscreen) return _picture();
    final picture = widget.expanded
        ? Expanded(
            child: Center(
              child: AspectRatio(aspectRatio: _aspect, child: _picture()),
            ),
          )
        : AspectRatio(
            aspectRatio: _aspect.clamp(1.0, 2.4).toDouble(),
            child: _picture(),
          );
    return Card(
      color: const Color(0xFF1A232D),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              uiText('Anteprima Blender', 'Blender preview'),
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            picture,
          ],
        ),
      ),
    );
  }
}
