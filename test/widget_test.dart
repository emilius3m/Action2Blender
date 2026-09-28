import 'package:action2blender/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('connection and recording controls are visible', (tester) async {
    tester.view.physicalSize = const Size(1920, 1080);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const Action2BlenderApp());
    expect(find.text('Connessione a Blender'), findsOneWidget);
    expect(find.text('Movimento'), findsOneWidget);
    expect(find.text('Ripresa'), findsOneWidget);
    expect(find.text('Rec'), findsOneWidget);
  });
}
