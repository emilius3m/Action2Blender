import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';

/// Italian on Italian phones; English for every other system language.
String uiText(String italian, String english) {
  String language;
  try {
    language = WidgetsBinding.instance.platformDispatcher.locale.languageCode;
  } on FlutterError {
    language = ui.PlatformDispatcher.instance.locale.languageCode;
  }
  return language == 'it' ? italian : english;
}
