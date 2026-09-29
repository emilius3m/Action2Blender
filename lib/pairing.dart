import 'dart:io';
import 'app_language.dart';

class PairingDetails {
  const PairingDetails(this.host, this.port, this.token);

  final String host;
  final int port;
  final String token;
}

PairingDetails parsePairingQr(String value) {
  final uri = Uri.tryParse(value);
  if (uri == null ||
      uri.scheme != 'a2b' ||
      uri.userInfo.isNotEmpty ||
      uri.path.isNotEmpty ||
      uri.fragment.isNotEmpty ||
      uri.queryParameters.length != 2 ||
      uri.queryParametersAll.values.any((values) => values.length != 1) ||
      uri.queryParameters['v'] != '1' ||
      !RegExp(
        r'^[A-Za-z0-9_-]{8,64}$',
      ).hasMatch(uri.queryParameters['t'] ?? '')) {
    throw FormatException(
      uiText('QR Action2Blender non valido', 'Invalid Action2Blender QR code'),
    );
  }
  final address = InternetAddress.tryParse(uri.host);
  if (address == null || address.type != InternetAddressType.IPv4) {
    throw FormatException(
      uiText(
        'Il QR deve contenere un indirizzo IPv4',
        'The QR code must contain an IPv4 address',
      ),
    );
  }
  if (address.isLoopback ||
      address.address == '0.0.0.0' ||
      address.rawAddress.first >= 224) {
    throw FormatException(
      uiText(
        'Indirizzo del PC non raggiungibile',
        'PC address is not reachable',
      ),
    );
  }
  final port = uri.port;
  if (port < 1 || port > 65535) {
    throw FormatException(
      uiText('Porta non valida nel QR', 'Invalid port in QR code'),
    );
  }
  return PairingDetails(address.address, port, uri.queryParameters['t']!);
}
