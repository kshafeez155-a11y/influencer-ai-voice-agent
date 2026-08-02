import pyaudio


def main() -> int:
    audio = pyaudio.PyAudio()

    try:
        print("")
        print("=" * 72)
        print("WINDOWS AUDIO DEVICES")
        print("=" * 72)

        default_input = None
        default_output = None

        try:
            default_input = (
                audio.get_default_input_device_info()
            )
        except OSError:
            pass

        try:
            default_output = (
                audio.get_default_output_device_info()
            )
        except OSError:
            pass

        if default_input:
            print(
                "[DEFAULT MICROPHONE] "
                f"{default_input['index']} — "
                f"{default_input['name']}"
            )
        else:
            print("[DEFAULT MICROPHONE] Not found")

        if default_output:
            print(
                "[DEFAULT SPEAKER] "
                f"{default_output['index']} — "
                f"{default_output['name']}"
            )
        else:
            print("[DEFAULT SPEAKER] Not found")

        print("")
        print("-" * 72)
        print("ALL DEVICES")
        print("-" * 72)

        for index in range(audio.get_device_count()):
            device = audio.get_device_info_by_index(index)

            input_channels = int(
                device.get("maxInputChannels", 0)
            )
            output_channels = int(
                device.get("maxOutputChannels", 0)
            )

            device_types: list[str] = []

            if input_channels > 0:
                device_types.append("MIC")

            if output_channels > 0:
                device_types.append("SPEAKER")

            if not device_types:
                continue

            print(
                f"[{index}] "
                f"{'/'.join(device_types):11} | "
                f"{device['name']} | "
                f"Input channels: {input_channels} | "
                f"Output channels: {output_channels}"
            )

        print("=" * 72)
        return 0

    finally:
        audio.terminate()


if __name__ == "__main__":
    raise SystemExit(main())