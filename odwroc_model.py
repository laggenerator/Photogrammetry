import sys
import math
import os


def rotate_ply_around_z(input_file, output_file, angle_degrees):
    angle_rad = math.radians(angle_degrees)

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    header_end = 0
    vertex_count = 0
    in_header = True
    vertex_start = 0

    for i, line in enumerate(lines):
        line_stripped = line.strip()

        if in_header:
            if line_stripped.startswith('element vertex'):
                vertex_count = int(line_stripped.split()[-1])
            elif line_stripped == 'end_header':
                header_end = i
                vertex_start = i + 1
                in_header = False
        else:
            if vertex_start <= i < vertex_start + vertex_count:
                parts = line_stripped.split()
                if len(parts) >= 3:
                    try:
                        x = float(parts[0])
                        y = float(parts[1])
                        z = float(parts[2])

                        x_new = x * math.cos(angle_rad) - \
                            y * math.sin(angle_rad)
                        y_new = x * math.sin(angle_rad) + \
                            y * math.cos(angle_rad)
                        z_new = z

                        parts[0] = str(x_new)
                        parts[1] = str(y_new)
                        parts[2] = str(z_new)

                        lines[i] = ' '.join(parts) + '\n'
                    except ValueError:
                        continue

    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print(f"Model PLY obrócony o {angle_degrees} stopni wokół osi Z")
    print(f"Zapisano do: {output_file}")


def rotate_obj_around_z(input_file, output_file, angle_degrees):
    angle_rad = math.radians(angle_degrees)

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        line_stripped = line.strip()

        if line_stripped.startswith('v ') and len(line_stripped.split()) >= 4:
            parts = line_stripped.split()

            try:
                x = float(parts[1])
                y = float(parts[2])
                z = float(parts[3])

                x_new = x * math.cos(angle_rad) - y * math.sin(angle_rad)
                y_new = x * math.sin(angle_rad) + y * math.cos(angle_rad)
                z_new = z

                # Zachowaj inne komponenty jeśli istnieją (np. współrzędne tekstury w wierszach 'vt')
                parts[1] = str(x_new)
                parts[2] = str(y_new)
                parts[3] = str(z_new)

                lines[i] = ' '.join(parts) + '\n'
            except ValueError:
                continue

        # Obróć też normalne (vn) jeśli istnieją
        elif line_stripped.startswith('vn ') and len(line_stripped.split()) >= 4:
            parts = line_stripped.split()

            try:
                nx = float(parts[1])
                ny = float(parts[2])
                nz = float(parts[3])

                nx_new = nx * math.cos(angle_rad) - ny * math.sin(angle_rad)
                ny_new = nx * math.sin(angle_rad) + ny * math.cos(angle_rad)
                nz_new = nz

                parts[1] = str(nx_new)
                parts[2] = str(ny_new)
                parts[3] = str(nz_new)

                lines[i] = ' '.join(parts) + '\n'
            except ValueError:
                continue

    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print(f"Model OBJ obrócony o {angle_degrees} stopni wokół osi Z")
    print(f"Zapisano do: {output_file}")


def rotate_model(input_file, output_file, angle_degrees):
    file_ext = os.path.splitext(input_file)[1].lower()

    if file_ext == '.ply':
        rotate_ply_around_z(input_file, output_file, angle_degrees)
    elif file_ext == '.obj':
        rotate_obj_around_z(input_file, output_file, angle_degrees)
    else:
        print(f"Nieobsługiwany format pliku: {file_ext}")
        print("Obsługiwane formaty: .ply, .obj")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print(
            "Użycie: python3 odwroc_model.py plik.[ply|obj] [kąt_w_stopniach] [plik_wyjsciowy]")
        print("Przykłady:")
        print("  python3 odwroc_model.py model.ply")
        print("  python3 odwroc_model.py model.obj 90")
        print("  python3 odwroc_model.py model.obj -45 rotated_model.obj")
        print("Domyślnie: 180 stopni (odwrócenie)")
        sys.exit(1)

    input_file = sys.argv[1]

    if not os.path.exists(input_file):
        print(f"Plik {input_file} nie istnieje!")
        sys.exit(1)

    # Domyślne wartości
    angle = 180
    output_file = None

    # Parsowanie argumentów
    if len(sys.argv) >= 3:
        # Sprawdź czy drugi argument to kąt czy plik wyjściowy
        try:
            angle = float(sys.argv[2])
            arg_is_angle = True
        except ValueError:
            arg_is_angle = False

        if arg_is_angle:
            # sys.argv[2] to kąt
            if len(sys.argv) >= 4:
                # sys.argv[3] to plik wyjściowy
                output_file = sys.argv[3]
        else:
            # sys.argv[2] to plik wyjściowy
            output_file = sys.argv[2]
            # użyj domyślnego kąta 180

    # Jeśli nie podano pliku wyjściowego, wygeneruj nazwę
    if not output_file:
        base_name = os.path.splitext(input_file)[0]
        ext = os.path.splitext(input_file)[1]
        output_file = f"{base_name}_rotated_{angle}deg{ext}"

    # Sprawdź czy plik wyjściowy już istnieje
    if os.path.exists(output_file) and output_file != input_file:
        print(f"UWAGA: Plik {output_file} już istnieje!")
        response = input("Nadpisać? (t/n): ")
        if response.lower() != 't':
            print("Anulowano.")
            sys.exit(0)

    rotate_model(input_file, output_file, angle)


if __name__ == "__main__":
    main()
