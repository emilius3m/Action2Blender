import 'dart:async';

import 'package:action2blender/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized()
        .platformDispatcher
        .localeTestValue = const Locale(
      'it',
    );
  });
  tearDown(() {
    TestWidgetsFlutterBinding.ensureInitialized().platformDispatcher
        .clearLocaleTestValue();
  });

  testWidgets('restores the last PC address and port', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    const channel = MethodChannel('org.action2blender/control');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(channel, (call) async {
      if (call.method == 'getConnectionSettings') {
        return {'host': '192.168.1.24', 'port': 47000};
      }
      return null;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));

    await tester.pumpWidget(const Action2BlenderApp());
    await tester.pump();
    final fields = tester
        .widgetList<TextField>(find.byType(TextField))
        .toList();
    expect(fields[0].controller?.text, '192.168.1.24');
    expect(fields[1].controller?.text, '47000');
    expect(fields[2].controller?.text, isEmpty);
  });

  testWidgets('uses English labels on an English phone', (tester) async {
    tester.binding.platformDispatcher.localeTestValue = const Locale('en');
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const Action2BlenderApp());
    expect(find.text('Connect to Blender'), findsOneWidget);
    expect(find.text('Blender preview'), findsOneWidget);
    expect(find.text('Recenter'), findsOneWidget);
    expect(find.text('Scan Blender QR code'), findsOneWidget);
  });

  testWidgets('landscape shows controls over the full screen preview', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const Action2BlenderApp());
    expect(find.text('Action2Blender · 16:9'), findsOneWidget);
    expect(find.text('Rec'), findsOneWidget);
    expect(find.text('Azzera'), findsOneWidget);
    expect(find.text('Collega'), findsOneWidget);
    expect(find.text('Anteprima Blender'), findsNothing);
    await tester.tap(find.text('Collega'));
    await tester.pump();
    expect(find.text('Connessione a Blender'), findsOneWidget);
    expect(find.text('Movimento'), findsOneWidget);
    expect(find.text('Scansiona QR di Blender'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('phone layout shows viewport and controls without overflow', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const Action2BlenderApp());
    expect(find.text('Anteprima Blender'), findsOneWidget);
    expect(find.text('Azzera'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('tablet layout fits at its narrowest width', (tester) async {
    tester.view.physicalSize = const Size(900, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const Action2BlenderApp());
    expect(find.text('Action2Blender · 16:9'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('phone rotates to landscape controls without overflow', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(832, 384);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const Action2BlenderApp());
    expect(find.text('Action2Blender · 16:9'), findsOneWidget);
    expect(find.text('Rec'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('QR button shows progress and scanner error beside connection', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    const channel = MethodChannel('org.action2blender/control');
    final scannerResult = Completer<String?>();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) {
          if (call.method == 'scanQr') return scannerResult.future;
          return null;
        });
    addTearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null);
    });

    await tester.pumpWidget(const Action2BlenderApp());
    await tester.tap(find.text('Scansiona QR di Blender'));
    await tester.pump();
    expect(find.text('Preparazione lettore QR…'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    scannerResult.completeError(
      PlatformException(code: 'QR_SCAN', message: 'Lettore QR non disponibile'),
    );
    await tester.pump();
    expect(find.text('Lettore QR non disponibile'), findsOneWidget);
    expect(find.text('Scansiona QR di Blender'), findsOneWidget);
  });

  testWidgets('connected landscape fits camera and joystick controls', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(832, 384);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    const channel = MethodChannel('org.action2blender/events');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(channel, (call) async => null);
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));

    await tester.pumpWidget(const Action2BlenderApp());
    await messenger.handlePlatformMessage(
      'org.action2blender/events',
      const StandardMethodCodec().encodeSuccessEnvelope({
        'status': 'Camera pronta',
        'connected': true,
        'tracking': true,
        'centered': true,
        'viewportPort': 0,
        'recording': false,
        'paused': false,
      }),
      (_) {},
    );
    await tester.pump();
    expect(find.text('Sposta'), findsOneWidget);
    expect(find.text('Ruota'), findsOneWidget);
    expect(find.byTooltip('Nuova camera dalla vista 3D'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('connected portrait tablet fits navigation beside the preview', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(900, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    const channel = MethodChannel('org.action2blender/events');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(channel, (call) async => null);
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));

    await tester.pumpWidget(const Action2BlenderApp());
    await messenger.handlePlatformMessage(
      'org.action2blender/events',
      const StandardMethodCodec().encodeSuccessEnvelope({
        'status': 'Camera pronta',
        'connected': true,
        'tracking': true,
        'centered': true,
        'viewportPort': 0,
        'recording': false,
        'paused': false,
      }),
      (_) {},
    );
    await tester.pump();
    expect(find.text('Sposta'), findsOneWidget);
    expect(find.text('Ruota'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
