import 'package:action2blender/pairing.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('reads Blender pairing QR', () {
    final details = parsePairingQr('a2b://192.168.1.3:45767?v=1&t=12345678');
    expect(details.host, '192.168.1.3');
    expect(details.port, 45767);
    expect(details.token, '12345678');
  });

  test('rejects other QR codes and incomplete pairing', () {
    for (final value in [
      'https://example.com',
      'a2b://example.com:45767?v=1&t=12345678',
      'a2b://192.168.1.3?v=1&t=12345678',
      'a2b://192.168.1.3:45767?v=1&t=short',
      'a2b://192.168.1.3:45767?v=2&t=12345678',
    ]) {
      expect(() => parsePairingQr(value), throwsFormatException);
    }
  });
}
