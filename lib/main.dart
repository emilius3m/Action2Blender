import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'app_language.dart';
import 'control_joystick.dart';
import 'pairing.dart';
import 'viewport_preview.dart';

void main() => runApp(const Action2BlenderApp());

class Action2BlenderApp extends StatelessWidget {
  const Action2BlenderApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Action2Blender',
    debugShowCheckedModeBanner: false,
    supportedLocales: const [Locale('en'), Locale('it')],
    localizationsDelegates: const [
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    theme: ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorSchemeSeed: const Color(0xFF75D8C7),
    ),
    home: const CameraControlPage(),
  );
}

class CameraControlPage extends StatefulWidget {
  const CameraControlPage({super.key});

  @override
  State<CameraControlPage> createState() => _CameraControlPageState();
}

class _CameraControlPageState extends State<CameraControlPage> {
  static const _control = MethodChannel('org.action2blender/control');
  static const _events = EventChannel('org.action2blender/events');
  final _host = TextEditingController();
  final _port = TextEditingController(text: '45767');
  final _token = TextEditingController();
  StreamSubscription<dynamic>? _subscription;
  String _status = uiText('Avvio del tracciamento…', 'Starting tracking…');
  String _connectedHost = '';
  String _connectedToken = '';
  String? _qrFeedback;
  int _viewportPort = 0;
  bool _scanningQr = false;
  bool _immersive = false;
  bool _showLandscapeSettings = false;
  bool _tracking = false,
      _connected = false,
      _recording = false,
      _paused = false,
      _recenterPending = false,
      _cameraError = false,
      _centered = false;
  double _scale = 1.0;
  double _stabilization = 0.25;
  int _countdownSetting = 0;
  int _countdownRemaining = 0;
  int _frame = 0;
  int _recoverableTakes = 0;
  bool _preparing = false;
  double _lensMm = 50.0;
  double _focusDistance = 10.0;
  double _fstop = 2.8;
  double _pinchBaseLens = 50.0;
  DateTime _lastOpticsSent = DateTime.fromMillisecondsSinceEpoch(0);
  double _moveX = 0, _moveY = 0, _lookX = 0, _lookY = 0, _lift = 0;

  @override
  void initState() {
    super.initState();
    unawaited(_restoreConnectionSettings());
    _subscription = _events.receiveBroadcastStream().listen((event) {
      if (!mounted || event is! Map) return;
      setState(() {
        _status = event['status']?.toString() ?? _status;
        if (_scanningQr && _status.startsWith('Inquadra il QR')) {
          _qrFeedback = _status;
        }
        _tracking = event['tracking'] == true;
        _connected = event['connected'] == true;
        _viewportPort = event['viewportPort'] is int
            ? event['viewportPort'] as int
            : 0;
        _centered = _connected && event['centered'] == true;
        _recenterPending = _connected && event['recenterPending'] == true;
        _cameraError = event['cameraError'] == true;
        _recording = event['recording'] == true;
        _preparing = event['preparing'] == true;
        _countdownRemaining = event['countdown'] is int
            ? event['countdown'] as int
            : 0;
        _countdownSetting = event['countdownSetting'] is int
            ? event['countdownSetting'] as int
            : _countdownSetting;
        _frame = event['frame'] is int ? event['frame'] as int : _frame;
        _recoverableTakes = event['recoverableTakes'] is int
            ? event['recoverableTakes'] as int
            : _recoverableTakes;
        _lensMm = event['lens'] is num
            ? (event['lens'] as num).toDouble()
            : _lensMm;
        _focusDistance = event['focusDistance'] is num
            ? (event['focusDistance'] as num).toDouble()
            : _focusDistance;
        _fstop = event['fstop'] is num
            ? (event['fstop'] as num).toDouble()
            : _fstop;
        _paused = event['paused'] == true;
        if (event['stabilization'] is num) {
          _stabilization = (event['stabilization'] as num)
              .toDouble()
              .clamp(0.0, 1.0)
              .toDouble();
        }
      });
    });
  }

  Future<void> _restoreConnectionSettings() async {
    final initialHost = _host.text;
    final initialPort = _port.text;
    try {
      final saved = await _control.invokeMapMethod<String, Object?>(
        'getConnectionSettings',
      );
      if (!mounted || saved == null) return;
      final host = saved['host'];
      final port = saved['port'];
      final countdown = saved['countdown'];
      if (_host.text == initialHost && host is String) _host.text = host;
      if (_port.text == initialPort &&
          port is int &&
          port > 0 &&
          port <= 65535) {
        _port.text = port.toString();
      }
      if (countdown is int && {0, 3, 5}.contains(countdown)) {
        setState(() => _countdownSetting = countdown);
      }
    } on MissingPluginException {
      // Settings are unavailable outside Android, including widget tests.
    } on PlatformException {
      // Connection fields remain editable when the local settings cannot be read.
    }
  }

  @override
  void dispose() {
    if (_immersive) {
      unawaited(SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge));
    }
    _subscription?.cancel();
    _host.dispose();
    _port.dispose();
    _token.dispose();
    super.dispose();
  }

  Future<bool> _call(String method, [Map<String, Object?>? args]) async {
    try {
      await _control.invokeMethod<Object?>(method, args);
      return true;
    } on PlatformException catch (error) {
      if (mounted) {
        setState(
          () => _status =
              error.message ??
              uiText('Operazione non riuscita', 'Operation failed'),
        );
      }
      return false;
    }
  }

  Future<void> _scanQr() async {
    if (_scanningQr) return;
    setState(() {
      _scanningQr = true;
      _qrFeedback = uiText('Apertura lettore QR…', 'Opening QR scanner…');
    });
    try {
      final raw = await _control.invokeMethod<String>('scanQr');
      if (!mounted) return;
      if (raw == null) {
        setState(
          () => _qrFeedback = uiText('Scansione annullata', 'Scan cancelled'),
        );
        return;
      }
      final details = parsePairingQr(raw);
      _host.text = details.host;
      _port.text = details.port.toString();
      _token.text = details.token;
      setState(() {
        _centered = false;
        _status = uiText(
          'QR letto: connessione a Blender…',
          'QR read: connecting to Blender…',
        );
        _qrFeedback = uiText(
          'QR letto. Connessione a Blender…',
          'QR read. Connecting to Blender…',
        );
      });
      _connect();
    } on FormatException catch (error) {
      if (mounted) setState(() => _qrFeedback = error.message);
    } on PlatformException catch (error) {
      if (mounted) {
        setState(
          () => _qrFeedback =
              error.message ??
              uiText(
                'Scansione non riuscita. Inserisci IP e codice a mano.',
                'Scan failed. Enter the IP and pairing code manually.',
              ),
        );
      }
    } on MissingPluginException {
      if (mounted) {
        setState(
          () => _qrFeedback = uiText(
            'Lettore QR non disponibile in questa installazione. Aggiorna l’app.',
            'QR scanner unavailable in this installation. Update the app.',
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _scanningQr = false);
    }
  }

  Future<void> _recenter() async {
    _stopNavigation();
    if (mounted) setState(() => _centered = false);
    await _call('recenter');
  }

  Future<void> _createCamera(String mode) async {
    _stopNavigation();
    if (mounted) {
      setState(() {
        _centered = false;
        _showLandscapeSettings = false;
      });
    }
    await _call('createCamera', {'mode': mode});
  }

  Future<void> _sendNavigation() async {
    try {
      await _control.invokeMethod<void>('setNavigation', {
        'moveX': _moveX,
        'moveY': _moveY,
        'lookX': _lookX,
        'lookY': _lookY,
        'lift': _lift,
      });
    } on PlatformException {
      // Connection status is reported by the native event stream.
    }
  }

  void _stopNavigation() {
    _moveX = _moveY = _lookX = _lookY = _lift = 0;
    unawaited(_sendNavigation());
  }

  void _sendOptics({bool force = false}) {
    if (!_recording) return;
    final now = DateTime.now();
    if (!force && now.difference(_lastOpticsSent).inMilliseconds < 50) return;
    _lastOpticsSent = now;
    unawaited(
      _call('setOptics', {
        'lens': _lensMm,
        'focus_distance': _focusDistance,
        'fstop': _fstop,
      }),
    );
  }

  Widget _pinchPreview(Widget child) => GestureDetector(
    behavior: HitTestBehavior.translucent,
    onScaleStart: (_) => _pinchBaseLens = _lensMm,
    onScaleUpdate: (details) {
      if (!_recording || details.pointerCount < 2) return;
      setState(
        () => _lensMm = (_pinchBaseLens * details.scale).clamp(12.0, 200.0),
      );
      _sendOptics();
    },
    onScaleEnd: (_) => _sendOptics(force: true),
    child: child,
  );

  Widget _opticsControls() => _card(uiText('Obiettivo', 'Lens'), [
    Text(
      '${uiText('Focale', 'Focal length')}: ${_lensMm.toStringAsFixed(1)} mm',
    ),
    Slider(
      value: _lensMm.clamp(12.0, 200.0),
      min: 12,
      max: 200,
      onChanged: _recording ? (value) => setState(() => _lensMm = value) : null,
      onChangeEnd: _recording ? (_) => _sendOptics(force: true) : null,
    ),
    Text(
      '${uiText('Distanza di fuoco', 'Focus distance')}: ${_focusDistance.toStringAsFixed(2)} BU',
    ),
    Slider(
      value: _focusDistance.clamp(0.1, 100.0),
      min: 0.1,
      max: 100,
      onChanged: _recording
          ? (value) => setState(() => _focusDistance = value)
          : null,
      onChangeEnd: _recording ? (_) => _sendOptics(force: true) : null,
    ),
    Text('${uiText('Diaframma', 'Aperture')}: f/${_fstop.toStringAsFixed(1)}'),
    Slider(
      value: _fstop.clamp(1.0, 22.0),
      min: 1,
      max: 22,
      onChanged: _recording ? (value) => setState(() => _fstop = value) : null,
      onChangeEnd: _recording ? (_) => _sendOptics(force: true) : null,
    ),
    Text(
      uiText(
        'Pizzica l’anteprima con due dita per cambiare focale.',
        'Pinch the preview with two fingers to change focal length.',
      ),
    ),
  ]);

  Widget _countdownControls() => Wrap(
    spacing: 8,
    children: [0, 3, 5]
        .map(
          (seconds) => ChoiceChip(
            label: Text(
              seconds == 0
                  ? uiText('Senza conto', 'No countdown')
                  : '$seconds s',
            ),
            selected: _countdownSetting == seconds,
            onSelected: _recording || _preparing
                ? null
                : (_) {
                    setState(() => _countdownSetting = seconds);
                    unawaited(_call('setCountdown', {'seconds': seconds}));
                  },
          ),
        )
        .toList(),
  );

  Widget _liftButton(IconData icon, double direction, bool enabled) => Listener(
    onPointerDown: enabled
        ? (_) {
            _lift = direction;
            unawaited(_sendNavigation());
          }
        : null,
    onPointerUp: (_) {
      _lift = 0;
      unawaited(_sendNavigation());
    },
    onPointerCancel: (_) {
      _lift = 0;
      unawaited(_sendNavigation());
    },
    child: Container(
      width: 42,
      height: 42,
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.68),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white54),
      ),
      child: Icon(icon, color: enabled ? Colors.white : Colors.white38),
    ),
  );

  Widget _navigationControls(bool enabled) => Row(
    mainAxisAlignment: MainAxisAlignment.spaceBetween,
    children: [
      ControlJoystick(
        label: uiText('Sposta', 'Move'),
        enabled: enabled,
        onChanged: (value) {
          _moveX = value.dx;
          _moveY = -value.dy;
          unawaited(_sendNavigation());
        },
      ),
      Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _liftButton(Icons.arrow_upward, 1, enabled),
          const SizedBox(height: 8),
          _liftButton(Icons.arrow_downward, -1, enabled),
        ],
      ),
      ControlJoystick(
        label: uiText('Ruota', 'Rotate'),
        enabled: enabled,
        onChanged: (value) {
          _lookX = value.dx;
          _lookY = value.dy;
          unawaited(_sendNavigation());
        },
      ),
    ],
  );

  void _connect() {
    _stopNavigation();
    setState(() => _centered = false);
    final port = int.tryParse(_port.text);
    if (_host.text.trim().isEmpty ||
        _token.text.trim().isEmpty ||
        port == null ||
        port < 1 ||
        port > 65535) {
      setState(
        () => _status = uiText(
          'Inserisci IP, porta e codice mostrati in Blender',
          'Enter the IP, port and code shown in Blender',
        ),
      );
      return;
    }
    _connectedHost = _host.text.trim();
    _connectedToken = _token.text.trim();
    _call('connect', {
      'host': _connectedHost,
      'port': port,
      'token': _connectedToken,
    });
  }

  Widget _card(String title, List<Widget> children) => Card(
    color: const Color(0xFF1A232D),
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          ...children,
        ],
      ),
    ),
  );

  Widget _indicator(String title, bool active) => Chip(
    avatar: Icon(
      active ? Icons.check_circle : Icons.circle_outlined,
      size: 18,
      color: active ? const Color(0xFF75D8C7) : Colors.white54,
    ),
    label: Text(title),
  );

  void _syncSystemUi(bool landscape) {
    if (_immersive == landscape) return;
    _immersive = landscape;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(
        SystemChrome.setEnabledSystemUIMode(
          landscape ? SystemUiMode.immersiveSticky : SystemUiMode.edgeToEdge,
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final landscape =
        MediaQuery.orientationOf(context) == Orientation.landscape;
    _syncSystemUi(landscape);
    return Scaffold(
      appBar: landscape ? null : AppBar(title: const Text('Action2Blender')),
      body: LayoutBuilder(
        builder: (context, constraints) {
          final connection = Column(
            children: [
              _card(uiText('Connessione a Blender', 'Connect to Blender'), [
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _host,
                        decoration: InputDecoration(
                          labelText: uiText('IP del PC', 'PC IP address'),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    SizedBox(
                      width: 90,
                      child: TextField(
                        controller: _port,
                        keyboardType: TextInputType.number,
                        decoration: InputDecoration(
                          labelText: uiText('Porta', 'Port'),
                        ),
                      ),
                    ),
                  ],
                ),
                TextField(
                  controller: _token,
                  decoration: InputDecoration(
                    labelText: uiText('Codice di abbinamento', 'Pairing code'),
                  ),
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: _recording || _scanningQr ? null : _scanQr,
                  icon: _scanningQr
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.qr_code_scanner),
                  label: Text(
                    _scanningQr
                        ? uiText(
                            'Preparazione lettore QR…',
                            'Preparing QR scanner…',
                          )
                        : uiText(
                            'Scansiona QR di Blender',
                            'Scan Blender QR code',
                          ),
                  ),
                ),
                if (_qrFeedback != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Text(_qrFeedback!),
                  ),
                FilledButton.icon(
                  onPressed: _connect,
                  icon: const Icon(Icons.wifi),
                  label: Text(uiText('Connetti', 'Connect')),
                ),
              ]),
              _card(uiText('Movimento', 'Movement'), [
                Text(
                  '${uiText('Scala', 'Scale')}: ${_scale.toStringAsFixed(1)}×',
                ),
                Slider(
                  value: _scale,
                  min: 0.1,
                  max: 10.0,
                  divisions: 99,
                  onChanged: _recording
                      ? null
                      : (value) => setState(() => _scale = value),
                  onChangeEnd: _recording
                      ? null
                      : (value) => _call('setScale', {'value': value}),
                ),
                Text(
                  '${uiText('Stabilizzazione live', 'Live stabilization')}: ${(_stabilization * 100).round()}%',
                ),
                Slider(
                  value: _stabilization,
                  min: 0,
                  max: 1,
                  divisions: 20,
                  onChanged: _recording
                      ? null
                      : (value) => setState(() => _stabilization = value),
                  onChangeEnd: _recording
                      ? null
                      : (value) => _call('setStabilization', {'value': value}),
                ),
                Text(
                  uiText(
                    'Più stabile significa una risposta leggermente più lenta. 0% la disattiva.',
                    'Higher stabilization adds a little delay. 0% turns it off.',
                  ),
                ),
                OutlinedButton.icon(
                  onPressed:
                      _connected &&
                          _tracking &&
                          !_recording &&
                          !_recenterPending
                      ? _recenter
                      : null,
                  icon: const Icon(Icons.center_focus_strong),
                  label: Text(uiText('Azzera', 'Recenter')),
                ),
              ]),
              if (_connected)
                _card(uiText('Nuova camera', 'New camera'), [
                  FilledButton.icon(
                    onPressed: _tracking && !_recording && !_recenterPending
                        ? () => _createCamera('view')
                        : null,
                    icon: const Icon(Icons.add_a_photo),
                    label: Text(
                      uiText(
                        'Dalla vista 3D di Blender',
                        'From Blender 3D View',
                      ),
                    ),
                  ),
                  OutlinedButton.icon(
                    onPressed: _tracking && !_recording && !_recenterPending
                        ? () => _createCamera('subject')
                        : null,
                    icon: const Icon(Icons.center_focus_strong),
                    label: Text(
                      uiText(
                        'Inquadra oggetto selezionato',
                        'Frame selected object',
                      ),
                    ),
                  ),
                ]),
            ],
          );
          final recording = Column(
            children: [
              _card(uiText('Ripresa', 'Recording'), [
                Wrap(
                  spacing: 8,
                  children: [
                    _indicator('Blender', _connected),
                    _indicator(uiText('Tracciamento', 'Tracking'), _tracking),
                    _indicator('Camera', _centered),
                  ],
                ),
                Text(_status),
                if (_recording || _preparing)
                  Text(
                    _countdownRemaining > 0
                        ? '${uiText('Tra', 'In')} $_countdownRemaining s'
                        : '${uiText('Frame', 'Frame')}: $_frame',
                  ),
                if (_connected &&
                    !_centered &&
                    !_recenterPending &&
                    !_cameraError)
                  Text(
                    uiText(
                      'Premi Azzera per fissare la camera di partenza.',
                      'Press Recenter to set the starting camera position.',
                    ),
                  ),
                const SizedBox(height: 18),
                Text(uiText('Conto alla rovescia', 'Countdown')),
                _countdownControls(),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: FilledButton.icon(
                    onPressed:
                        _recording ||
                            _preparing ||
                            (_connected && _tracking && _centered)
                        ? () => _call(
                            _recording || _preparing
                                ? 'stopRecording'
                                : 'startRecording',
                          )
                        : null,
                    icon: Icon(
                      _recording || _preparing
                          ? Icons.stop
                          : Icons.fiber_manual_record,
                    ),
                    label: Text(
                      _preparing
                          ? uiText('Annulla', 'Cancel')
                          : _recording
                          ? 'Stop'
                          : 'Rec',
                    ),
                  ),
                ),
                if (_paused)
                  Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: FilledButton.tonalIcon(
                      onPressed: _tracking
                          ? () => _call('resumeRecording')
                          : null,
                      icon: const Icon(Icons.play_arrow),
                      label: Text(
                        uiText('Riprendi senza salto', 'Resume without jump'),
                      ),
                    ),
                  ),
              ]),
              _opticsControls(),
              if (_recoverableTakes > 0)
                _card(uiText('Take recuperate', 'Recovered takes'), [
                  Text(
                    uiText(
                      '$_recoverableTakes riprese interrotte sono conservate sul telefono.',
                      '$_recoverableTakes interrupted takes are kept on this phone.',
                    ),
                  ),
                  OutlinedButton(
                    onPressed: _connected
                        ? () => _call('sendRecoveredTakes')
                        : null,
                    child: Text(uiText('Invia a Blender', 'Send to Blender')),
                  ),
                ]),
              Padding(
                padding: const EdgeInsets.all(8),
                child: Text(
                  uiText(
                    'Tieni libera la fotocamera posteriore per il tracciamento.',
                    'Keep the rear camera clear for tracking.',
                  ),
                ),
              ),
            ],
          );
          final tablet = constraints.maxWidth >= 900;
          final preview = ViewportPreview(
            connected: _connected,
            host: _connectedHost,
            port: _viewportPort,
            token: _connectedToken,
            width: tablet ? 960 : 640,
            expanded: tablet,
          );
          if (landscape) {
            final fullscreenPreview = ViewportPreview(
              connected: _connected,
              host: _connectedHost,
              port: _viewportPort,
              token: _connectedToken,
              width: 960,
              fullscreen: true,
            );
            return Stack(
              fit: StackFit.expand,
              children: [
                _pinchPreview(fullscreenPreview),
                SafeArea(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12),
                          decoration: BoxDecoration(
                            color: Colors.black.withValues(alpha: 0.68),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: Row(
                            children: [
                              Text(
                                _recording && constraints.maxWidth < 1000
                                    ? 'A2B'
                                    : 'Action2Blender · 16:9',
                              ),
                              if (_recording) ...[
                                const SizedBox(width: 8),
                                Text(
                                  '$_frame · ${_lensMm.toStringAsFixed(0)} mm · f/${_fstop.toStringAsFixed(1)}',
                                ),
                              ],
                              const SizedBox(width: 16),
                              Icon(
                                _connected ? Icons.wifi : Icons.wifi_off,
                                size: 18,
                                color: _connected
                                    ? const Color(0xFF75D8C7)
                                    : Colors.white70,
                              ),
                              const SizedBox(width: 6),
                              Icon(
                                _tracking
                                    ? Icons.radio_button_checked
                                    : Icons.radio_button_unchecked,
                                size: 18,
                                color: _tracking
                                    ? const Color(0xFF75D8C7)
                                    : Colors.white70,
                              ),
                              const SizedBox(width: 6),
                              Tooltip(
                                message: _centered
                                    ? uiText('Camera pronta', 'Camera ready')
                                    : uiText('Premi Azzera', 'Press Recenter'),
                                child: Icon(
                                  Icons.videocam,
                                  size: 18,
                                  color: _centered
                                      ? const Color(0xFF75D8C7)
                                      : Colors.white70,
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Text(
                                  _status,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                              IconButton(
                                tooltip: uiText(
                                  'Nuova camera dalla vista 3D',
                                  'New camera from 3D View',
                                ),
                                onPressed:
                                    _connected &&
                                        _tracking &&
                                        !_recording &&
                                        !_recenterPending
                                    ? () => _createCamera('view')
                                    : null,
                                icon: const Icon(Icons.add_a_photo),
                              ),
                              TextButton.icon(
                                onPressed: () => setState(() {
                                  _stopNavigation();
                                  _showLandscapeSettings = true;
                                }),
                                icon: const Icon(Icons.settings),
                                label: Text(
                                  _connected
                                      ? uiText('Opzioni', 'Options')
                                      : uiText('Collega', 'Connect'),
                                ),
                              ),
                            ],
                          ),
                        ),
                        const Spacer(),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 6,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.black.withValues(alpha: 0.72),
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Row(
                            children: [
                              Text(
                                '${uiText('Scala', 'Scale')} ${_scale.toStringAsFixed(1)}×',
                              ),
                              SizedBox(
                                width: 160,
                                child: Slider(
                                  value: _scale,
                                  min: 0.1,
                                  max: 10.0,
                                  divisions: 99,
                                  onChanged: _recording
                                      ? null
                                      : (value) =>
                                            setState(() => _scale = value),
                                  onChangeEnd: _recording
                                      ? null
                                      : (value) =>
                                            _call('setScale', {'value': value}),
                                ),
                              ),
                              const Spacer(),
                              OutlinedButton.icon(
                                onPressed:
                                    _connected &&
                                        _tracking &&
                                        !_recording &&
                                        !_recenterPending
                                    ? _recenter
                                    : null,
                                icon: const Icon(Icons.center_focus_strong),
                                label: Text(uiText('Azzera', 'Recenter')),
                              ),
                              if (_paused) ...[
                                const SizedBox(width: 8),
                                OutlinedButton.icon(
                                  onPressed: _tracking
                                      ? () => _call('resumeRecording')
                                      : null,
                                  icon: const Icon(Icons.play_arrow),
                                  label: Text(uiText('Riprendi', 'Resume')),
                                ),
                              ],
                              const SizedBox(width: 8),
                              FilledButton.icon(
                                onPressed:
                                    _recording ||
                                        _preparing ||
                                        (_connected && _tracking && _centered)
                                    ? () => _call(
                                        _recording || _preparing
                                            ? 'stopRecording'
                                            : 'startRecording',
                                      )
                                    : null,
                                icon: Icon(
                                  _recording || _preparing
                                      ? Icons.stop
                                      : Icons.fiber_manual_record,
                                ),
                                label: Text(
                                  _preparing
                                      ? uiText('Annulla', 'Cancel')
                                      : _recording
                                      ? 'Stop'
                                      : 'Rec',
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                if (_connected && _centered)
                  Positioned(
                    left: 18,
                    right: 18,
                    bottom: 104,
                    child: _navigationControls(_tracking && !_paused),
                  ),
                if (_showLandscapeSettings)
                  Positioned.fill(
                    child: ColoredBox(
                      color: Colors.black54,
                      child: Align(
                        alignment: Alignment.centerRight,
                        child: SizedBox(
                          width: (constraints.maxWidth * 0.55).clamp(
                            300.0,
                            440.0,
                          ),
                          child: Material(
                            color: const Color(0xFF10171F),
                            child: SafeArea(
                              child: ListView(
                                padding: const EdgeInsets.all(8),
                                children: [
                                  Align(
                                    alignment: Alignment.centerRight,
                                    child: IconButton(
                                      tooltip: uiText(
                                        'Chiudi opzioni',
                                        'Close options',
                                      ),
                                      onPressed: () => setState(
                                        () => _showLandscapeSettings = false,
                                      ),
                                      icon: const Icon(Icons.close),
                                    ),
                                  ),
                                  connection,
                                  _card(
                                    uiText('Conto alla rovescia', 'Countdown'),
                                    [_countdownControls()],
                                  ),
                                  _opticsControls(),
                                  if (_recoverableTakes > 0)
                                    _card(
                                      uiText(
                                        'Take recuperate',
                                        'Recovered takes',
                                      ),
                                      [
                                        Text('$_recoverableTakes'),
                                        OutlinedButton(
                                          onPressed: _connected
                                              ? () =>
                                                    _call('sendRecoveredTakes')
                                              : null,
                                          child: Text(
                                            uiText(
                                              'Invia a Blender',
                                              'Send to Blender',
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            );
          }
          if (!tablet) {
            return SafeArea(
              child: ListView(
                padding: const EdgeInsets.all(12),
                children: _connected
                    ? [
                        _pinchPreview(preview),
                        if (_centered)
                          _navigationControls(_tracking && !_paused),
                        recording,
                        connection,
                      ]
                    : [connection, preview, recording],
              ),
            );
          }
          return SafeArea(
            child: Row(
              children: [
                Expanded(
                  flex: 7,
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      children: [
                        Expanded(child: preview),
                        if (_centered)
                          _navigationControls(_tracking && !_paused),
                      ],
                    ),
                  ),
                ),
                Expanded(
                  flex: 3,
                  child: ListView(
                    padding: const EdgeInsets.all(12),
                    children: [recording, connection],
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
