# Action2Blender

**English** · [Italiano](README.it.md)

Use an Android phone as a virtual camera for Blender: move the shot by hand or with on-screen controls, watch the preview on the phone, and record every shot as a separate take.

> **Current version: 0.2.0 beta 1.** Download the APK and the add-on ZIP from the [Releases page](https://github.com/emilius3m/Action2Blender/releases). Always use the app and add-on from the **same release**: 0.2 does not connect to the 0.1 add-on, and vice versa.

## Requirements

- Blender 5.2 (tested with 5.2.1) on a PC.
- An ARCore-compatible Android phone ([supported devices](https://developers.google.com/ar/devices)). So far it has been tested on a Samsung Galaxy S25 Ultra.
- PC and phone on the same local network, with the connection allowed by the PC firewall on the private network.

## Installation

1. From the Releases page, download `Action2Blender-addon-0.2.0.zip` and `Action2Blender-0.2.0-beta.1.apk`.
2. In Blender, open **Edit → Preferences → Add-ons**, choose **Install from Disk** from the **⌄** menu at the top right, select the ZIP and enable **Action2Blender**. The panel is in **3D Viewport → Sidebar (N) → Action2Blender**. If you are upgrading from an earlier version, save your scene and restart Blender.
3. Install the APK on the phone, open **Action2Blender** and allow camera access. Android may ask you to install or update Google Play Services for AR.

If Android refuses the update because the installed app has a different signature, **do not uninstall it while there are takes Blender has not confirmed yet**: they are stored only in the app's private storage.

The app follows the phone language (Italian on Italian phones, English otherwise); the Blender panel is in English. This guide uses the English app labels.

## Connect the phone

1. Open your scene in Blender. To use an existing camera, pick it in the **Camera** field of the Action2Blender panel. The camera must not have a parent object or active constraints. You can also create a new camera from the app once connected.
2. **16:9 framing** is on by default and sets the scene resolution to 16:9 when the connection starts; turn it off to keep the scene's format. Press **Start phone connection**: the panel shows a QR code, the PC's IP address, the port and a temporary pairing code.
3. In the app, press **Scan Blender QR code**; the scanner is built into the app. Alternatively, enter the IP, port and code and press **Connect**. The app remembers the last PC IP and port after a restart; enter the current pairing code again. If the PC has several network connections, check that the IP shown in the panel is the one the phone can reach.
4. Wait for **Tracking active**. To start from the chosen camera, press **Recenter**: its current framing becomes the starting point. Or, in the **New camera** card, choose **From Blender 3D View** or **Frame selected object**. Wait for **Camera ready** before recording.

## Move and record the camera

- **Physical movement.** Move and turn the phone and the camera follows. The phone's vertical matches Blender's, so panning keeps the horizon level and walking moves the camera horizontally even when it is tilted. **Scale** multiplies translation only (1× = one real metre per Blender unit), not rotation.
- **On-screen controls.** After **Camera ready**, **Move** (forward, back and sideways, always horizontal), **Rotate** (pan and tilt) and the up/down buttons appear. They add to the physical movement, work with the phone fixed on a mount, and are recorded in the take.
- **Preview.** The phone shows the camera view rendered by Blender. In landscape it fills the screen with the controls over the video; on tablets the controls sit alongside.
- **Recording.** Press **Rec** to start and **Stop** to finish. The screen stays on while tracking. The take appears under **Recorded takes** in the Blender panel as a separate Action, starting at the current frame; earlier takes are never overwritten. Select one in the panel and save the `.blend` file.
- **Tracking loss.** If ARCore loses tracking or the app is paused, the take is suspended. When tracking returns, press **Resume without jump**.
- **Network.** After **Stop** the take stays on the phone until Blender confirms it has been saved. If Wi-Fi drops, press **Connect** again (or scan the QR code) and the take is sent again. You may need to press **Recenter** again.

### Stabilization

There are two separate filters; if both are on, the take is smoothed twice.

- **Live stabilization** (in the app, 25% by default): filters the phone pose before the preview and the recording. High values make intentional moves respond a little more slowly. It can only be changed outside Rec; 0% turns it off.
- **Stabilize after Stop** (in Blender, on with **Strength** 0.5): after Stop, creates a second, stabilized Action next to the original, which is never modified. **Stabilize selected take** creates a new stabilized version of a take already recorded.

## Troubleshooting

| Problem | Quick check |
| --- | --- |
| The phone does not connect | PC and phone on the same network, correct IP in the panel, connection allowed by the firewall on the private network. |
| "Update the Action2Blender app on your phone" or "Update or reload the Action2Blender add-on" | The app and add-on come from different releases: install both from the same release and restart Blender. |
| The camera does not move or Rec is disabled | Wait for tracking and **Camera ready**. With an existing camera, pick it in the panel and press **Recenter**. The camera must have no parent object and no active constraints. |
| The selected take does not play back | Timeline markers bound to cameras choose the active camera during playback. |
| No preview | Keep a 3D Viewport open in Blender and check the firewall: the preview uses a second local port besides the connection port. |
| Controls stop responding after opening another file | Press **Stop phone connection**, then **Start phone connection**, and reconnect the phone. |
| The take does not appear after Stop | Check the message in the app and wait for Blender's confirmation. Do not uninstall the app while a take is pending. |

## Known limitations of this beta

- The preview, joysticks, creating a camera from the app and the new vertical alignment have been verified with automated tests and in Blender; the full test on the phone is still in progress. Other Android phones have not been tested yet.
- Opening another `.blend` file while connected stops command processing until you restart the connection from the panel.
- A take pending on the phone can no longer be saved if Blender is restarted, or the connection is restarted from the panel, in the meantime.
- The phone does not reconnect by itself after a network drop.
- Very long takes (over about 15 minutes) can exceed the message size limit.
- After turning the camera with the joystick, physical movement still follows the direction it had at **Recenter**.
- Takes animate position and rotation, not focal length. Camera parents and constraints are not supported.

## Development

The code has three parts: the Flutter interface (`lib/`), ARCore tracking and networking in Kotlin (`android/app/src/main/kotlin/`), and the Blender add-on in Python (`addon/action2blender/`). For tests, builds and development status see [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md); the camera design is in [CAMERA_DESIGN.md](CAMERA_DESIGN.md). Both are in Italian.

The original code is released under the [MIT license](LICENSE). ARCore and the other dependencies keep their own licenses; see [THIRD_PARTY.md](THIRD_PARTY.md).
