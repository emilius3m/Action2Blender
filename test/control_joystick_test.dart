import 'package:action2blender/control_joystick.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('joystick reports direction and stops on release', (
    tester,
  ) async {
    final values = <Offset>[];
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: ControlJoystick(
              label: 'Sposta',
              enabled: true,
              onChanged: values.add,
            ),
          ),
        ),
      ),
    );

    final center = tester.getCenter(find.byType(GestureDetector));
    final gesture = await tester.startGesture(center);
    await gesture.moveBy(const Offset(32, -28));
    await tester.pump();
    expect(values.last.dx, greaterThan(0));
    expect(values.last.dy, lessThan(0));
    await gesture.up();
    await tester.pump();
    expect(values.last, Offset.zero);
  });
}
