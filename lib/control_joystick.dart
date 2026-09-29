import 'package:flutter/material.dart';

class ControlJoystick extends StatefulWidget {
  const ControlJoystick({
    super.key,
    required this.label,
    required this.enabled,
    required this.onChanged,
  });

  final String label;
  final bool enabled;
  final ValueChanged<Offset> onChanged;

  @override
  State<ControlJoystick> createState() => _ControlJoystickState();
}

class _ControlJoystickState extends State<ControlJoystick> {
  static const double diameter = 106;
  Offset position = Offset.zero;

  @override
  void didUpdateWidget(ControlJoystick oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.enabled && !widget.enabled) {
      position = Offset.zero;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        widget.onChanged(Offset.zero);
      });
    }
  }

  void update(Offset local) {
    if (!widget.enabled) return;
    final value = Offset(
      (local.dx - diameter / 2) / (diameter * 0.36),
      (local.dy - diameter / 2) / (diameter * 0.36),
    );
    final length = value.distance;
    final limited = length > 1 ? value / length : value;
    setState(() => position = limited);
    widget.onChanged(limited);
  }

  void release() {
    if (position == Offset.zero) return;
    setState(() => position = Offset.zero);
    widget.onChanged(Offset.zero);
  }

  @override
  Widget build(BuildContext context) => Column(
    mainAxisSize: MainAxisSize.min,
    children: [
      Text(widget.label, style: const TextStyle(fontSize: 12)),
      const SizedBox(height: 3),
      GestureDetector(
        behavior: HitTestBehavior.opaque,
        onPanDown: (details) => update(details.localPosition),
        onPanUpdate: (details) => update(details.localPosition),
        onPanEnd: (_) => release(),
        onPanCancel: release,
        child: Container(
          width: diameter,
          height: diameter,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: Colors.black.withValues(alpha: 0.62),
            border: Border.all(color: Colors.white54, width: 2),
          ),
          child: Stack(
            alignment: Alignment.center,
            children: [
              const Icon(Icons.add, color: Colors.white38, size: 30),
              Transform.translate(
                offset: position * (diameter * 0.36),
                child: Container(
                  width: 38,
                  height: 38,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: widget.enabled
                        ? const Color(0xFF75D8C7)
                        : Colors.grey,
                    boxShadow: const [
                      BoxShadow(color: Colors.black54, blurRadius: 5),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    ],
  );
}
