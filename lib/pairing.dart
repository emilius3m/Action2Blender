import 'dart:io';

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
    throw const FormatException('QR Action2Blender non valido');
  }
  final address = InternetAddress.tryParse(uri.host);
  if (address == null || address.type != InternetAddressType.IPv4) {
    throw const FormatException('Il QR deve contenere un indirizzo IPv4');
  }
  if (address.isLoopback ||
      address.address == '0.0.0.0' ||
      address.rawAddress.first >= 224) {
    throw const FormatException('Indirizzo del PC non raggiungibile');
  }
  final port = uri.port;
  if (port < 1 || port > 65535) {
    throw const FormatException('Porta non valida nel QR');
  }
  return PairingDetails(address.address, port, uri.queryParameters['t']!);
}
