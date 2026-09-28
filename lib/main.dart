import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

void main() => runApp(const Action2BlenderApp());

class Action2BlenderApp extends StatelessWidget {
  const Action2BlenderApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Action2Blender',
    debugShowCheckedModeBanner: false,
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
  String _status = 'Avvio del tracciamento…';
  bool _tracking = false,
      _connected = false,
      _recording = false,
      _paused = false;
  double _scale = 1.0;

  @override
  void initState() {
    super.initState();
    _subscription = _events.receiveBroadcastStream().listen((event) {
      if (!mounted || event is! Map) return;
      setState(() {
        _status = event['status']?.toString() ?? _status;
        _tracking = event['tracking'] == true;
        _connected = event['connected'] == true;
        _recording = event['recording'] == true;
        _paused = event['paused'] == true;
      });
    });
  }

  @override
  void dispose() {
    _subscription?.cancel();
    _host.dispose();
    _port.dispose();
    _token.dispose();
    super.dispose();
  }

  Future<void> _call(String method, [Map<String, Object?>? args]) async {
    try {
      await _control.invokeMethod<Object?>(method, args);
    } on PlatformException catch (error) {
      if (mounted) {
        setState(() => _status = error.message ?? 'Operazione non riuscita');
      }
    }
  }

  void _connect() {
    final port = int.tryParse(_port.text);
    if (_host.text.trim().isEmpty ||
        _token.text.trim().isEmpty ||
        port == null) {
      setState(
        () => _status = 'Inserisci IP, porta e codice mostrati in Blender',
      );
      return;
    }
    _call('connect', {
      'host': _host.text.trim(),
      'port': port,
      'token': _token.text.trim(),
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

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Action2Blender')),
    body: SafeArea(
      child: LayoutBuilder(
        builder: (context, constraints) {
          final connection = Column(
            children: [
              _card('Connessione a Blender', [
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _host,
                        decoration: const InputDecoration(
                          labelText: 'IP del PC',
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    SizedBox(
                      width: 90,
                      child: TextField(
                        controller: _port,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(labelText: 'Porta'),
                      ),
                    ),
                  ],
                ),
                TextField(
                  controller: _token,
                  decoration: const InputDecoration(
                    labelText: 'Codice di abbinamento',
                  ),
                ),
                const SizedBox(height: 12),
                FilledButton.icon(
                  onPressed: _connect,
                  icon: const Icon(Icons.wifi),
                  label: const Text('Connetti'),
                ),
              ]),
              _card('Movimento', [
                Text('Scala: ${_scale.toStringAsFixed(1)}×'),
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
                OutlinedButton.icon(
                  onPressed: _connected && _tracking && !_recording
                      ? () => _call('recenter')
                      : null,
                  icon: const Icon(Icons.center_focus_strong),
                  label: const Text('Azzera'),
                ),
              ]),
            ],
          );
          final recording = Column(
            children: [
              _card('Ripresa', [
                Wrap(
                  spacing: 8,
                  children: [
                    _indicator('Blender', _connected),
                    _indicator('Tracking', _tracking),
                  ],
                ),
                Text(_status),
                const SizedBox(height: 18),
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: FilledButton.icon(
                    onPressed: _recording || (_connected && _tracking)
                        ? () => _call(
                            _recording ? 'stopRecording' : 'startRecording',
                          )
                        : null,
                    icon: Icon(
                      _recording ? Icons.stop : Icons.fiber_manual_record,
                    ),
                    label: Text(_recording ? 'Stop' : 'Rec'),
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
                      label: const Text('Riprendi senza salto'),
                    ),
                  ),
              ]),
              const Padding(
                padding: EdgeInsets.all(8),
                child: Text(
                  'Guarda la scena sul monitor di Blender. Tieni libera la fotocamera posteriore.',
                  style: TextStyle(color: Colors.white70),
                ),
              ),
            ],
          );
          if (constraints.maxWidth < 650) {
            return ListView(
              padding: const EdgeInsets.all(12),
              children: [connection, recording],
            );
          }
          return Row(
            children: [
              Expanded(
                flex: 5,
                child: ListView(
                  padding: const EdgeInsets.all(12),
                  children: [connection],
                ),
              ),
              Expanded(
                flex: 4,
                child: ListView(
                  padding: const EdgeInsets.all(12),
                  children: [recording],
                ),
              ),
            ],
          );
        },
      ),
    ),
  );
}
