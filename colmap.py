import os
import subprocess
import pycolmap
from pathlib import Path
import open3d as o3d
import numpy as np
import sys
import shutil
import hashlib
import logging
import yaml

# Ścieżki
katalog = Path(__file__).resolve().parent
zdjecia_dir = katalog / Path("work/zdjecia")
output_dir = katalog / Path("work/output")
reco_dir = katalog / Path("work/output/reconstructions")
undistort_dir = katalog / Path("work/undistort")
dependencies_dir = katalog / Path("dependencies")
chmury_dir = katalog / Path("chmury")
zdjecia_hash = katalog / Path("work/img_hash")
# Relatywne
local_dir = Path(__file__).parent
local_dir_output = local_dir / "work/output"
local_dir_zdjecia = local_dir / "work/zdjecia"

logi = katalog / Path("work/log")
opcje = katalog / Path("work/options.yaml")
# tworzenie katalogow
output_dir.mkdir(exist_ok=True)
reco_dir.mkdir(exist_ok=True)
undistort_dir.mkdir(exist_ok=True)
chmury_dir.mkdir(exist_ok=True)
zdjecia_hash.touch(exist_ok=True)
logi.touch(exist_ok=True)

colmap_exec = dependencies_dir / "colmap"

podana_nazwa = None
n_watkow = 8  # Ile wątków
uzywacGPU = False  # Czy robic z GPU
zlozonosc = 0
uzywacSekwencyjnego = False
testProcesow = False  # Używać procesów colmap (1) czy pycolmap (0)

# konfiguracja pliku do logowania
logging.basicConfig(
    filename=str(logi),
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)

# czy jest w ogole plik z ustawieniami
if not opcje.exists():
    raise FileNotFoundError(f"Nie znaleziono pliku opcji YAML: {opcje}")

#configs["Options"][0] to slownik najszybszych ustawien, 1 srednich a 2 takich mocarnyyyych, 3 to wlasne jakies custom
with open(str(opcje), "r") as f:
    configs = yaml.safe_load(f)

# oblicza hasz katalogu z czasow, program sam sprawdzi czy katalog ze zdjeciami sie zmienil i
# na podstawie tego zrobi co trzeba


def haszuj_katalog(path: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(path)).encode())
            h.update(str(p.stat().st_mtime_ns).encode())
    return h.hexdigest()


# hasz dalej potrzebny nawet jesli -f, bo na koncu trzeba nadpisac
hash_nowy = haszuj_katalog(zdjecia_dir)
if (not "-f" in sys.argv and not '-r' in sys.argv):
    with open(str(zdjecia_hash)) as f:
        hash_stary = f.readline().strip()

    czy_zmieniono_zdjecia = (hash_nowy != hash_stary)

    # program juz sie wykonal wczesniej, caly, na tych zdjeciach
#   if(not czy_zmieniono_zdjecia):
#     print("Program już został wykonany na tych zdjeciach! Aby wymusic użyj opcji -f.")
#     sys.exit(0)
#   else: #jesli mamy nowe zdjecia to wyczyscmy katalogi
#     if output_dir.exists():
#       shutil.rmtree(output_dir)
#       output_dir.mkdir(exist_ok=True)
#       reco_dir.mkdir(exist_ok=True)

if "-r" in sys.argv or "-f" in sys.argv:
    print("Podano opcję -r/-f! Usuwam starą rekonstrukcję.")
    if output_dir.exists():
        shutil.rmtree(output_dir)
        output_dir.mkdir(exist_ok=True)
        reco_dir.mkdir(exist_ok=True)

if "-o" in sys.argv:
    gdzie_nazwa = sys.argv.index("-o") + 1
    podana_nazwa = sys.argv[gdzie_nazwa] if gdzie_nazwa < len(
        sys.argv) else None
    print("Podana nazwa:", podana_nazwa, "Szukaj w chmurka :)")
else:
    print("Nie podano nazwy wyjsciowego modulu. Szukaj w",
          str((undistort_dir / "pmvs/models")))
if "-l" in sys.argv:
    gdzie_zlozonosc = sys.argv.index("-l") + 1
    zlozonosc = int(sys.argv[gdzie_zlozonosc]) if gdzie_zlozonosc < len(sys.argv) else 0
    if(zlozonosc < 0 or zlozonosc > 3):
      zlozonosc = 0
      print(f"Podano nieprawidlowy poziom! Opcje to 0 - najszybsze, 1 - srednie, 2 - dokladne. 3 - niestandardowe. Domyslnie ustawiono 0")
    else:
        print(f"Podano poziom rekonstrukcji {zlozonosc}")
else:
    print("Nie podano poziomu zlozonosci. Przyjęto 0 (najszybszy).")
if "-nthreads" in sys.argv:
    print(f"Używamy {n_watkow} wątków!")
    ile_watkow_idx = sys.argv.index("-nthreads") + 1
    n_watkow = int(sys.argv[ile_watkow_idx])
if "-seq" in sys.argv:
    print(f"Używamy sekwencyjnego matchowania!")
    uzywacSekwencyjnego = True
if "-gpu" in sys.argv: #nie podane -- CPU, podane z 0 -- CPU, podane z 1 -- GPU
    idx = sys.argv.index("-gpu") + 1
    if idx < len(sys.argv):
        uzywacGPU = bool(int(sys.argv[idx]))

# nie wydaje sie potrzebne razem z rozwiazaniem z haszami, bo jedyna sytuacja jaka
# zachodzi to albo te same, albo stare zdjecia -- po co wywoływać jeszcze raz cały program, albo
# nawet tylko jego czesc jesli nie zmienily sie zdjecia? Zresztą można z opcją -f.
# def czy_istnieje_rekonstrukcja():
#    ply_path = output_dir / "chmurka.PLY"
#
#    if reco_dir.exists() and ply_path.exists():
#        if any(reco_dir.iterdir()):
#            print("Znaleziono istniejącą rekonstrukcję")
#            return True
#    return False

# Parametry z options.yaml
config_level = configs["Options"][zlozonosc]
cmvs_images_per_cluster = config_level['cmvs_images_per_cluster']
cmvs_levels = config_level['level']
csize = config_level['csize']
max_features = config_level['max_features']
num_nearest_neighbors = config_level['num_nearest_neighbors']
num_checks = config_level['num_checks']
ba_global_max_num_iterations = config_level['ba_global_max_num_iterations']
threshold = config_level['threshold']
useVisData = config_level['useVisData']
sequence = config_level['sequence']
quad = config_level['quad']
maxAngle = config_level['maxAngle']


def colmap():

    logging.info(f"Poczatek colmapowania, plik {podana_nazwa}")

    reader_opts = pycolmap.ImageReaderOptions(
        camera_model='SIMPLE_RADIAL',
        default_focal_length_factor=1.0,  # użyj pełnej rozdzielczości obrazu
    )
    # Ekstrakcja ficzerów
    if (testProcesow):
        subprocess.run([
            "colmap",
            "feature_extractor",
            "--database_path", f"{local_dir_output / "bazunia.db"}",
            "--image_path", f"{local_dir_zdjecia}",
            "--FeatureExtraction.use_gpu", f"{uzywacGPU}",
            "--FeatureExtraction.num_threads", f"{n_watkow}",
            "--SiftExtraction.max_num_features", f"{max_features}"
        ], check=True)
    else:
        pycolmap.extract_features(
            database_path=output_dir / "bazunia.db",
            image_path=zdjecia_dir,
            camera_mode=pycolmap.CameraMode.AUTO,
            reader_options=reader_opts,
            sift_options=pycolmap.SiftExtractionOptions(
                num_threads=n_watkow,
                use_gpu=uzywacGPU,
                # max_num_features=configs["Options"][zlozonosc]['max_features']
            )
        )
    logging.info("Ekstrakcja detali zakończona pomyślnie")

    # logging.info("wyekstraktowano")
    #   Matching ficzerów
    if (uzywacSekwencyjnego):
        if (testProcesow):
            subprocess.run([
                # str(colmap_exec),
                "colmap",
                "sequential_matcher",
                "--database_path", f"{local_dir_output / "bazunia.db"}",
                "--FeatureMatching.use_gpu", f"{uzywacGPU}",
                "--FeatureMatching.num_threads", f"{n_watkow}",
                "--FeatureMatching.guided_matching",  "1",
                "--FeatureMatching.max_num_matches", "8192"
            ], check=True)
        else:
            pycolmap.match_sequential(
                database_path=output_dir / "bazunia.db",
                sift_options=pycolmap.SiftMatchingOptions(
                    num_threads=n_watkow,
                    use_gpu=uzywacGPU,
                    guided_matching=True,
                )
            )
    else:
        if (testProcesow):
            subprocess.run([
                "colmap",
                "vocab_tree_matcher",
                "--database_path", f"{local_dir_output / "bazunia.db"}",
                "--FeatureMatching.use_gpu", f"{uzywacGPU}",
                "--FeatureMatching.num_threads", f"{n_watkow}",
                "--FeatureMatching.guided_matching",  "1",
                "--FeatureMatching.max_num_matches", "8192",
                "--VocabTreeMatching.num_checks",  f"{num_checks}",
                "--VocabTreeMatching.num_threads", f"{n_watkow}"
            ], check=True)
        else:
            pycolmap.match_vocabtree(
                database_path=output_dir / "bazunia.db",
                matching_options=pycolmap.VocabTreeMatchingOptions(
                    # ile najbliższych zdjec porownywac, ok 5-10
                    num_nearest_neighbors=configs["Options"][zlozonosc]['num_nearest_neighbors'],
                    # im wiecej tym lepiej ale wolniej : /
                    num_checks=configs["Options"][zlozonosc]['num_checks'],
                    num_threads=n_watkow,
                    vocab_tree_path=dependencies_dir / "vocab_tree_flickr100K_words32K.bin"
                )
            )
    logging.info("skonczono laczenie")

    if (testProcesow):
        (output_dir / "0").mkdir(exist_ok=True)
        subprocess.run([
            "colmap",
            "mapper",
            "--database_path", f"{local_dir_output / "bazunia.db"}",
            "--image_path", f"{local_dir_zdjecia}",
            "--output_path", f"{local_dir_output}",
            "--Mapper.num_threads", f"{n_watkow}",
            "--Mapper.ba_use_gpu", f"{uzywacGPU}"
        ], check=True)

        subprocess.run([
            "colmap",
            "model_converter",
            "--input_path", f"{local_dir_output / "0"}",
            "--output_path", f"{local_dir_output / "chmurka.PLY"}",
            "--output_type", "PLY"
        ], check=True)
    else:
        # Rekonstrukcja
        def wlacz_rekonstrukcje(zdjecia_dir, output_dir):
            rekonstrukcja = pycolmap.incremental_mapping(
                database_path=output_dir / "bazunia.db",
                image_path=zdjecia_dir,
                output_path=output_dir,
                options=pycolmap.IncrementalPipelineOptions(
                    num_threads=n_watkow,
                    ba_global_max_num_iterations=configs["Options"][zlozonosc]['ba_global_max_num_iterations'],
                    ba_use_gpu=uzywacGPU
                )
            )
            logging.info(
                f"koniec rekonstrukcji -- stworzylo ich {len(rekonstrukcja)}")
            return rekonstrukcja

        # Odpalajjj to
        # zwraca slownik, gdzie klucz to int takie id, jesli bedzie
        # pare rekonstrukcji to beda numerowane 0, 1, 2, ...
        rek_dict = wlacz_rekonstrukcje(zdjecia_dir, output_dir)

        # dla ulatwienia na poczatku wezmy tylko pierwsze
        if rek_dict[0] is not None:
            rek = rek_dict[0]
            print(f"Zrekonstruowano coś!")
            print(f"Zarejestrowano {len(rek.images)} zdjęć")
            print(f"Utworzono {len(rek.points3D)} punktów 3D")
            rek.export_PLY(output_dir / "chmurka.PLY")
            rek.write(output_dir / "reconstructions")


# depracted vvv
# if not czy_istnieje_rekonstrukcja():
if (undistort_dir / "pmvs").exists():
    shutil.rmtree(undistort_dir / "pmvs")
    logging.info(f"Usunięto katalog: {undistort_dir / "pmvs"}")

if "-f" in sys.argv or czy_zmieniono_zdjecia:
    logging.info(
        f"Czyszczenie katalogu roboczego colmap dla nowej rekonstrukcji")
    if (output_dir).exists():
        shutil.rmtree(output_dir)
        output_dir.mkdir(exist_ok=True)
        reco_dir.mkdir(exist_ok=True)
    logging.info(f"Wyczyszczono katalog roboczy")
    colmap()
else:
    print(f"Rekonstrukcja na tych zdjęciach już istnieje, pomijam rzadką rekonstrukcję")
    logging.info(
        f"Rekonstrukcja na tych zdjęciach już istnieje, pomijam rzadką rekonstrukcję")
# depracted vvv
# zaladowana_rekonstrukcja = pycolmap.Reconstruction(output_dir / "reconstructions")

# odzniekształcanie (undistort lol) zdjęć i zapisywanie ich i innych rzeczy
# (cale drzewo katalogowe) odpowiednio dla PMVS :D
pycolmap.undistort_images(
    output_path=undistort_dir,
    input_path=output_dir/"0",
    image_path=zdjecia_dir,
    output_type='PMVS',
)

# CMVS+PMVS2
logging.info(f"Uruchomienie procesu gęstej rekonstrukcji")

uzywacCMVS = False

# Liczba zdjęć do decyzji o użyciu CMVS
liczba_zdjec = len(list(zdjecia_dir.glob("*"))) if zdjecia_dir.exists() else 0
if liczba_zdjec >= 50:
    uzywacCMVS = True
    logging.info(f"Ustawiono tryb CMVS+PMVS")
else:
    logging.info(f"Ustawiono tryb PMVS")

if uzywacCMVS:
    logging.info(f"Użycie CMVS+PMVS2 dla {liczba_zdjec} zdjęć")

    pmvs_dir = undistort_dir / "pmvs"
    cmvs_exec = dependencies_dir / "cmvs"

    logging.info(f"Uruchamianie CMVS: {[
        str(cmvs_exec),
        str(pmvs_dir) + "/",
        str(cmvs_images_per_cluster),
        str(cmvs_levels),
    ]}")

    try:
        subprocess.run([
            str(cmvs_exec),
            str(pmvs_dir) + "/",
            str(cmvs_images_per_cluster),
            str(cmvs_levels),
        ], check=True)
        logging.info("CMVS zakończony pomyślnie")

    except subprocess.CalledProcessError as e:
        logging.error(f"[CMVS] Błąd: {e.stderr}")
        # Nie pykło robimy sam PMVS
        uzywacCMVS = False
        logging.info("Przełączam na tryb bez CMVS")

    genOption_exec = dependencies_dir / "genOption"

    if genOption_exec.exists():
        try:
            subprocess.run([
                str(genOption_exec),
                str(pmvs_dir) + "/",
                f"{str(cmvs_levels)} {str(csize)} {str(threshold)} 8 3 {str(n_watkow)}"
            ], check=True)
            logging.info("Wygenerowano pliki opcji dla klastrów")
        except subprocess.CalledProcessError as e:
            logging.error(f"genOption błąd: {e.stderr}")
            uzywacCMVS = False
    else:
        logging.warning(
            "Nie znaleziono genOption, kontynuuję z istniejącymi plikami opcji")

# Przygotowanie plików opcji
if uzywacCMVS:
    # Potrzebne pliki opcji dla każdego klastra
    option_files = list(pmvs_dir.glob("option-0*"))
    if not option_files:
        logging.warning(
            "Nie znaleziono plików opcji CMVS, przęłączanie na sam PMVS")
        uzywacCMVS = False

if not uzywacCMVS:
    logging.info(f"Użycie tylko PMVS2")

    with open(str(undistort_dir / "pmvs/opcje.txt"), 'w') as nowy:
        with open(str(undistort_dir / "pmvs/option-all"), 'r') as stary:
            for line in stary:
                parts = line.split()
                if not parts:
                    nowy.write(line)
                    continue
                haslo = parts[0]
                if haslo in configs["Options"][zlozonosc]:
                    nowy.write(
                        f"{haslo} {configs['Options'][zlozonosc][haslo]}\n")
                else:
                    nowy.write(line)

    option_files = [undistort_dir / "pmvs/opcje.txt"]

for option_file_path in option_files:
    with open(str(option_file_path), 'r') as f:
        lines = f.readlines()

    with open(str(option_file_path), 'w') as f:
        for line in lines:
            parts = line.split()
            if not parts:
                f.write(line)
                continue
            haslo = parts[0]
            if haslo in configs["Options"][zlozonosc]:
                f.write(f"{haslo} {configs['Options'][zlozonosc][haslo]}\n")
            else:
                f.write(line)

# Uruchom PMVS2
pmvs2_exec = dependencies_dir / "pmvs2"
pmvs_dir = undistort_dir / "pmvs"
prefix = undistort_dir / "pmvs/"  # colmap wyżej powinien go stworzyc
option_file = "opcje.txt"  # <- wewnatrz /undistort/pmvs
# dam go tu bo idk gdzie, zeby zobaczyc jakie sa opjce w pmvs2
# wystarczy uruchomic go i wyswietli ładnie :)

if uzywacCMVS:
    # Odpalamy PMVS dla każdego klastra
    logging.info(f"Uruchamianie PMVS2 na {len(option_files)} klastrach")
    for option_file_path in option_files:
        option_file_name = option_file_path.name
        logging.info(f"Przetwarzanie klastra: {option_file_name}")

        try:
            subprocess.run(
                [str(pmvs2_exec), str(prefix)+"/", option_file_name],
                check=True
            )
            logging.info(f"Klaster {option_file_name} zakończony")
        except subprocess.CalledProcessError as e:
            logging.error(f"PMVS2 błąd dla {option_file_name}: {e.stderr}")

    # Łączenie modeli
    models_dir = pmvs_dir / "models"
    if models_dir.exists():
        ply_files = list(models_dir.glob("*.ply"))

        if len(ply_files) > 1:
            logging.info(f"Łączenie {len(ply_files)} modeli z klastrów")

            # Jakiś merger z chata
            def combine_ply_files(input_files, output_file):
                if not input_files:
                    return

                # Analizuj format z pierwszego pliku
                vertex_format = []  # Lista tuple (typ, nazwa)
                has_colors = False
                has_normals = False
                has_quality = False

                with open(input_files[0], 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('property'):
                            parts = line.split()
                            if len(parts) >= 3:
                                prop_type = parts[1]
                                prop_name = parts[2]
                                vertex_format.append((prop_type, prop_name))

                                if 'red' in prop_name or 'green' in prop_name or 'blue' in prop_name:
                                    has_colors = True
                                elif 'nx' in prop_name or 'ny' in prop_name or 'nz' in prop_name:
                                    has_normals = True
                                elif 'quality' in prop_name:
                                    has_quality = True
                        elif line == 'end_header':
                            break

                # Zbierz wszystkie dane
                all_vertices = []  # Lista list wartości
                all_faces = []     # Lista krotek (3 indeksy)
                vertex_offset = 0

                for ply_file in input_files:
                    print(f"Łączenie: {ply_file.name}")

                    with open(ply_file, 'r') as f:
                        lines = f.readlines()

                    # Znajdź nagłówek i dane
                    header_end = 0
                    vertex_count = 0
                    face_count = 0

                    for i, line in enumerate(lines):
                        if line.startswith('element vertex'):
                            vertex_count = int(line.split()[-1])
                        elif line.startswith('element face'):
                            face_count = int(line.split()[-1])
                        elif line.strip() == 'end_header':
                            header_end = i + 1
                            break

                    # Wczytaj wierzchołki
                    vertex_start = header_end
                    for i in range(vertex_start, vertex_start + vertex_count):
                        if i < len(lines):
                            values = lines[i].strip().split()
                            # Konwertuj na odpowiednie typy
                            converted = []
                            for j, (prop_type, _) in enumerate(vertex_format):
                                if j < len(values):
                                    if prop_type in ['float', 'double']:
                                        converted.append(float(values[j]))
                                    elif prop_type in ['int', 'uchar', 'uint']:
                                        converted.append(int(values[j]))
                                    else:
                                        converted.append(values[j])
                                else:
                                    # Domyślne wartości jeśli brakuje
                                    if prop_type in ['float', 'double']:
                                        converted.append(0.0)
                                    elif prop_type in ['int', 'uchar', 'uint']:
                                        converted.append(0)
                                    else:
                                        converted.append('0')
                            all_vertices.append(converted)

                    # Wczytaj ściany
                    face_start = vertex_start + vertex_count
                    for i in range(face_start, face_start + face_count):
                        if i < len(lines):
                            parts = lines[i].strip().split()
                            if len(parts) >= 4 and parts[0] == '3':
                                try:
                                    v1 = int(parts[1]) + vertex_offset
                                    v2 = int(parts[2]) + vertex_offset
                                    v3 = int(parts[3]) + vertex_offset
                                    all_faces.append((v1, v2, v3))
                                except ValueError:
                                    continue  # Pomiń nieprawidłowe ściany

                    vertex_offset += vertex_count

                # Zapisz połączony plik
                with open(output_file, 'w') as f:
                    f.write("ply\n")
                    f.write("format ascii 1.0\n")
                    f.write(f"element vertex {len(all_vertices)}\n")

                    # Zapisz format wierzchołków
                    for prop_type, prop_name in vertex_format:
                        f.write(f"property {prop_type} {prop_name}\n")

                    f.write(f"element face {len(all_faces)}\n")
                    f.write("property list uchar int vertex_index\n")
                    f.write("end_header\n")

                    # Zapisz wierzchołki
                    for vertex in all_vertices:
                        f.write(" ".join(str(v) for v in vertex) + "\n")

                    # Zapisz ściany
                    for face in all_faces:
                        f.write(f"3 {face[0]} {face[1]} {face[2]}\n")

                print(f"Połączono {len(input_files)} plików")
                print(f"Łącznie wierzchołków: {len(all_vertices)}")
                print(f"Łącznie ścian: {len(all_faces)}")

            # Połącz wszystkie PLY
            combined_ply = models_dir / "combined.ply"
            combine_ply_files(ply_files, combined_ply)

            # Użyj połączonego modelu jako wynik
            stara_nazwa = "combined.ply"
        else:
            stara_nazwa = "option_0000.ply"
    else:
        stara_nazwa = option_file + ".ply"
else:
    option_file = "opcje.txt"
    logging.info(f"Uruchamianie PMVS2 z pojedynczym plikiem opcji")

    try:
        subprocess.run(
            [str(pmvs2_exec), str(pmvs_dir)+"/", option_file],
            check=True
        )
    except subprocess.CalledProcessError as e:
        logging.error(f"PMVS2 błąd: {e.stderr}")
        raise

    stara_nazwa = option_file + ".ply"

# Przenoszenie pliku do chmurek
if podana_nazwa is not None:
    stary_plik = pmvs_dir / "models" / stara_nazwa

    if stary_plik.exists():
        nowa_nazwa = Path(podana_nazwa).stem + ".ply"
        nowy_plik = chmury_dir / nowa_nazwa
        shutil.move(str(stary_plik), str(nowy_plik))
        logging.info(f"Przeniesiono model do: {nowy_plik}")
    else:
        logging.warning(f"Plik wynikowy nie istnieje: {stary_plik}")

# program się cały wykonał, zmieniamy hash
with open(str(zdjecia_hash), "w") as f:
    f.write(hash_nowy)

logging.info(f"Koniec procesu gęstej rekonstrukcji")
