import sys
import cv2 as cv
import time
import os
import subprocess
import glob
import re
import yaml
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QMessageBox
from pathlib import Path
import logging

sciezka_zdjecia = './work/zdjecia'
sciezka_ustawienia = './work/options.yaml'

katalog = Path(__file__).resolve().parent
logi = katalog / Path("work/log")
logging.basicConfig(
    filename=str(logi),
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)

# zaklada ze dostalo docelowa_rozdzielczosc w takiej samej orientacji (pion/poziom) co filmik (a tak jest w combo)


def ekstrakcjaKlatek(film_info, docelowa_liczba_klatek, docelowa_rozdzielczosc=None, log_callback=None, progress_callback=None):
    print(f'Otwieranie filmu: {film_info.sciezka}')
    if log_callback:
        log_callback(f'Otwieranie filmu: {film_info.sciezka}')

    film = cv.VideoCapture(film_info.sciezka)

    # Pobierz całkowitą liczbę klatek w filmie
    calkowita_liczba_klatek = film_info.liczba_klatek
    fps = film_info.fps

    # Oblicz interwał co ile klatek zapisywać
    if docelowa_liczba_klatek >= calkowita_liczba_klatek:
        interwal = 1  # Zapisz wszystkie klatki
    else:
        interwal = max(1, calkowita_liczba_klatek // docelowa_liczba_klatek)

    print(
        f'Film ma {calkowita_liczba_klatek} klatek, ekstrakcja co {interwal} klatki')
    if log_callback:
        log_callback(
            f'Film ma {calkowita_liczba_klatek} klatek, ekstrakcja co {interwal} klatki')
    print(f'Docelowa liczba klatek: {docelowa_liczba_klatek}')
    if log_callback:
        log_callback(f'Docelowa liczba klatek: {docelowa_liczba_klatek}')

    i = 0
    klatki = 0
    zapisane_klatki = 0
    ekstraktowaneh, ekstraktowanew = 0, 0
    os.makedirs('work/zdjecia', exist_ok=True)
    wyczyscZdjecia(log_callback)

    while (film.isOpened()):
        flag, klatka = film.read()
        if flag == False:
            break
        h, w, _ = klatka.shape
        wymiary = (w, h)
        if (docelowa_rozdzielczosc):  # okreslenie jakie wymiary (pionowe czy poziome)
            # to powinno byc zgodne z wymiarami filmu, bo tak sa zapisywane do combo
            wymiary = docelowa_rozdzielczosc

        # faktyczne pobranie klatki
        if klatki % interwal == 0 and zapisane_klatki < docelowa_liczba_klatek:
            resized_img = cv.resize(klatka, wymiary)
            cv.imwrite(f'./work/zdjecia/img_{i:04d}.jpg', resized_img)
            print(f'Zapisano ./work/zdjecia/img_{i:04d}.jpg')
            if log_callback:
                log_callback(f'Zapisano ./work/zdjecia/img_{i:04d}.jpg')
            i += 1
            zapisane_klatki += 1

        klatki += 1

        # wysyla jaki procent zrobiony
        if (progress_callback):
            progress_callback(
                int((zapisane_klatki*100)/docelowa_liczba_klatek))  # w procentach

        # Przerwij jeśli osiągnięto docelową liczbę klatek
        if zapisane_klatki >= docelowa_liczba_klatek:
            break

    film.release()
    return zapisane_klatki


def wyczyscZdjecia(log_callback=None):
    files = glob.glob('work/zdjecia/*')
    pomyslnieusuniete = 0
    nieusuniete = 0
    for f in files:
        try:
            if os.path.isfile(f):
                os.remove(f)
                pomyslnieusuniete += 1
        except Exception as e:
            print(f'Błąd przy usuwaniu zdjęcia -> {e}')
            if log_callback:
                log_callback(f'Błąd przy usuwaniu zdjęcia -> {e}')
            nieusuniete += 1
    print(f'Usunięto {pomyslnieusuniete}, nie udało się usunąć {nieusuniete}')
    if log_callback:
        log_callback(
            f'Usunięto {pomyslnieusuniete}, nie udało się usunąć {nieusuniete}')


class FilmInfo:
    def __init__(self, sciezka, szerokosc, wysokosc, liczba_klatek, fps):
        self.sciezka = sciezka
        self.szerokosc = szerokosc
        self.wysokosc = wysokosc
        self.liczba_klatek = liczba_klatek
        self.fps = fps


class ExtractionThread(QThread):
    progres = Signal(int)
    koniec = Signal(int)
    err = Signal(str)
    log_signal = Signal(str)

    def __init__(self, film_info, docelowa_liczba_klatek, docelowa_rozdzielczosc=None):
        super().__init__()
        self.film_info = film_info
        self.docelowa_liczba_klatek = docelowa_liczba_klatek
        self.docelowa_rozdzielczosc = docelowa_rozdzielczosc

    def run(self):
        try:
            wyekstraktowane_klatki = ekstrakcjaKlatek(
                self.film_info,
                self.docelowa_liczba_klatek,
                self.docelowa_rozdzielczosc,
                log_callback=self.log_signal.emit,
                progress_callback=self.progres.emit
            )
            self.koniec.emit(wyekstraktowane_klatki)
        except Exception as e:
            self.err.emit(str(e))


class ColmapThread(QThread):
    koniec = Signal(str)
    err = Signal(str)
    log_signal = Signal(str)

    def __init__(self, nazwa_modelu, ile_watkow, opcje_poziom, force, seq, czyGPU):
        super().__init__()
        self.nazwa_modelu = nazwa_modelu
        self.ile_watkow = ile_watkow
        self.opcje_poziom = opcje_poziom
        self.force = force
        self.seq = seq
        self.czyGPU = czyGPU

    def run(self):
        import subprocess
        try:
            cmd_args = ['python3', 'colmap.py', '-o', self.nazwa_modelu, '-nthreads',
                        str(self.ile_watkow), '-l', str(self.opcje_poziom), '-gpu', str(int(self.czyGPU))]
            if (self.force is True):
                print(f"Colmap działa w trybie wymuszonym")
                cmd_args.append('-f')
            if (self.seq is True):
                print(f"Używam matchowania sekwencyjnego")
                cmd_args.append('-seq')

            process = subprocess.Popen(
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            for line in process.stdout:
                line = line.strip()
                if line:
                    self.log_signal.emit(line)

            process.wait()

            if process.returncode == 0:
                self.koniec.emit(self.nazwa_modelu)
        except subprocess.CalledProcessError as e:
            self.err.emit(str(e))
        except Exception as e:
            self.err.emit(str(e))


class MeshingThread(QThread):
    koniec = Signal(str)
    err = Signal(str)
    log_signal = Signal(str)

    def __init__(self, nazwa_pliku, metoda):
        super().__init__()
        self.nazwa_pliku = nazwa_pliku
        self.metoda = metoda

    def run(self):
        import subprocess
        try:
            process = subprocess.Popen(
                ['python3', 'meshing.py', self.nazwa_pliku, str(self.metoda)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            for line in process.stdout:
                line = line.strip()
                if line:
                    self.log_signal.emit(line)

            process.wait()

            if process.returncode == 0:
                self.koniec.emit(self.nazwa_pliku)
        except subprocess.CalledProcessError as e:
            self.err.emit(str(e))
        except Exception as e:
            self.err.emit(str(e))


class MyWindow:
    def __init__(self):
        # wczytanie .ui
        ui_file = QFile("form.ui")
        ui_file.open(QFile.ReadOnly)
        loader = QUiLoader()
        self.window = loader.load(ui_file)
        ui_file.close()

        # timer rekonstrukcji
        self.start_time = None

        fotki = len(os.listdir(sciezka_zdjecia))
        # ustawienie pewnych rzeczy
        self.window.rekonstrukcjaStatusLabel.setHidden(True)
        self.window.rekonstrukcjaLabel2.setText(
            f'{fotki} zdjęć')
        self.window.wyborOpcji.clear()
        self.window.wyborOpcji.addItem("Największa wydajność", 0)
        self.window.wyborOpcji.addItem("Najlepsza jakość", 2)
        self.window.wyborOpcji.addItem("Połączenie obu światów", 1)
        self.window.wyborOpcji.addItem("Własne ustawienia", 3)
        # 0=ball pivoting, 1=poisson, 2=alpha shapes
        self.window.metodaWybor.clear()
        self.window.metodaWybor.addItem("Ball pivoting", 0)
        self.window.metodaWybor.addItem("Poisson", 1)
        self.window.metodaWybor.addItem("Alpha shapes", 2)
        watki = QThread.idealThreadCount()
        if (watki < 1):
            watki = 1
        self.window.wybierzLiczbeWatkow.setRange(1, watki)
        self.window.wybierzLiczbeWatkow.setValue(watki)  # ustawi na maks

        # atrybuty
        self.film = None
        self.typowe_rozdzielczosci = [
            (3840, 2160, "4K (3840x2160)"),
            (2560, 1440, "1440p (2560x1440)"),
            (1920, 1080, "1080p (1920x1080)"),
            (1280, 720, "720p (1280x720)"),
            (854, 480, "480p (854x480)")
        ]
        self.frame_count = fotki
        self.feature_count = []
        self.window.rekonstrukcjaAvgFeatureLabel.setHidden(True)
        self.window.rekonstrukcjaPointsCount.setHidden(True)

        #podłączenie przycisków
        self.window.wyszukiwanie.clicked.connect(self.przegladaj_film)
        self.window.startEkstrakcji.clicked.connect(self.start_extract)
        self.window.startRekonstrukcji.clicked.connect(self.start_colmap)
        self.window.startMeshowania.clicked.connect(self.start_mesh)
        self.window.zapiszUstawienia.clicked.connect(self.zapisz_ustawienia)

        print("plikow w zdjeciach:", len(os.listdir(sciezka_zdjecia)))
        print("wartosc:", self.window.wyborOpcji.currentData())

        #ograniczenia pól w ustawieniach
        

    def log(self, message):
        self.window.logWindow.append(message)
        # przewiń na sam dół, żeby zawsze pokazywało najnowsze wiadomości
        self.window.logWindow.verticalScrollBar().setValue(
            self.window.logWindow.verticalScrollBar().maximum()
        )
        pattern = r'Features:\s+(\d+)\s+\(SIFT\)'
        pattern2 = r'Łącznie wierzchołków:\s+(\d+)'
        # Logika wyświetlania statusu rekonstrukcji
        if ("Features: " in message and "(SIFT)" in message):
            matche = re.findall(pattern, message)
            features = [int(x) for x in matche]
            self.feature_count.extend(features)
            self.window.rekonstrukcjaAvgFeatureLabel.setHidden(False)
            if (len(self.feature_count) < int(self.frame_count)):
                self.window.rekonstrukcjaAvgFeatureLabel.setText(
                    f"Średnia liczba cech: {round(sum(self.feature_count) / len(self.feature_count))} ({round(100 * len(self.feature_count) / self.frame_count)}% zdjęć)")
            else:
                self.window.rekonstrukcjaAvgFeatureLabel.setText(
                    f"Średnia liczba cech: {round(sum(self.feature_count) / len(self.feature_count))}")
        elif ("Feature extraction" in message):
            self.start_time = time.time()
            self.window.rekonstrukcjaStatusLabel.setHidden(False)
            self.window.rekonstrukcjaStatusLabel.setText(
                "Status: Ekstrakcja detali ze zdjęć")
        elif ("Feature matching" in message):
            self.window.rekonstrukcjaStatusLabel.setText(
                f"Status: Matching detali ze zdjęć")
        elif ("Indexing image" in message):
            self.window.rekonstrukcjaStatusLabel.setText(
                f"Status: Indeksowanie zdjęć")
        elif ("Matching image" in message):
            self.window.rekonstrukcjaStatusLabel.setText(
                f"Status: Dopasowywanie zdjęć")
        elif ("Registering image" in message):
            self.window.rekonstrukcjaStatusLabel.setText(
                f"Status: Tworzenie rzadkiej rekonstrukcji ze zdjęć")
        elif ("Retriangulation and Global bundle adjustment" in message):
            self.window.rekonstrukcjaStatusLabel.setText(
                f"Status: Retriangulacja pozycji kamery")
        elif ("Undistorting image" in message):
            self.window.rekonstrukcjaStatusLabel.setText(
                f"Status: Usuwanie zniekształceń ze zdjęć")
        elif ("Reading bundle..." in message):
            self.window.rekonstrukcjaStatusLabel.setText(
                f"Status: Dzielenie zdjęć na klastry do gęstej rekonstrukcji")
        elif ("Summary of specified options" in message):
            self.window.rekonstrukcjaStatusLabel.setText(
                f"Status: Proces gęstej rekonstrukcji")
        elif ("Zrekonstruowano coś" in message):
            end_time = time.time() - self.start_time
            if end_time < 60:
                wiadomosc = f"{end_time:.2f}s"
            elif end_time < 3600:
                minuty = int(end_time // 60)
                sekundy = end_time % 60
                wiadomosc = f"{minuty}min {int(sekundy)}s"
            else:
                godziny = int(end_time // 3600)
                minuty = int((end_time % 3600) // 60)
                sekundy = end_time % 60
                wiadomosc = f"{godziny}h {minuty}min {int(sekundy)}s"

            self.window.rekonstrukcjaStatusLabel.setText(
                f"Status: Rekonstrukcja zakończona - upłynęło {wiadomosc}")

        elif ("Łącznie wierzchołków" in message):
            self.window.rekonstrukcjaPointsCount.setHidden(False)
            matche = re.findall(pattern2, message)
            features = [int(x) for x in matche]
            self.window.rekonstrukcjaPointsCount.setText(
                f"{max(features)} punktów w chmurze")

    def przegladaj_film(self):
        film_sciezka, _ = QFileDialog.getOpenFileName(
            self.window,
            'Wybierz plik wideo',
            '',
            'Video Files (*.mp4 *.avi *.mov *.mkv *.wmv)'
        )
        if film_sciezka:  # wybrano juz film
            # ile film ma klatek, jaka ma rozdzielczosc
            self.aktualizuj_info_klatek(film_sciezka)
            print(f'Film ({self.film.sciezka}, width: {self.film.szerokosc}, height: {self.film.wysokosc}, klatek: {self.film.liczba_klatek}, fps: {self.film.fps})')
            self.window.sciezkaFilmu.setText(film_sciezka)
            self.update_rozdzielczosc_combo()
            self.window.wybierzLiczbeKlatek.setRange(
                0, self.film.liczba_klatek)
            self.window.wybierzLiczbeKlatek.setValue(
                self.film.liczba_klatek)  # ustawi na maks

    # zapisuje do atrybutu self.film typu klasy FilmInfo informacje z podanej sciezki
    def aktualizuj_info_klatek(self, sciezka):
        film = cv.VideoCapture(sciezka)
        if not film.isOpened():
            self.show_error("Błąd otwarcia filmu")
            return

        klatki = int(film.get(cv.CAP_PROP_FRAME_COUNT))
        fps = film.get(cv.CAP_PROP_FPS)

        ret, frame = film.read()
        if not ret:
            self.show_error("Błąd odczytu klatki")
            return

        h, w = frame.shape[:2]

        self.film = FilmInfo(sciezka, w, h, klatki, fps)
        film.release()

    def update_rozdzielczosc_combo(self):
        if (self.film == None):
            return
        film_poziomy = True
        # i to moze byc pionowe/poziome
        wymiar = (self.film.szerokosc, self.film.wysokosc)
        if (wymiar[0] < wymiar[1]):
            film_poziomy = False
        self.window.wyborRozdzielczosci.clear()

        # OG rozdzielczość jako pierwsza pozycja
        self.window.wyborRozdzielczosci.addItem(
            f"Oryginalna ({max(wymiar)}x{min(wymiar)})",
            wymiar
        )
        # Dodawania rozdzielczosci <= od oryginalnej
        added_count = 0
        # w typowych width > height, ale niekoniecznie mamy film poziomy
        for width, height, name in self.typowe_rozdzielczosci:
            if not film_poziomy:
                width, height = height, width
            if width <= wymiar[0] and height <= wymiar[1]:
                self.window.wyborRozdzielczosci.addItem(name, (width, height))
                added_count += 1

    def ekstrakcja_zawies(self):
        self.window.startEkstrakcji.setEnabled(False)
        self.window.wyszukiwanie.setEnabled(False)
        # self.window.ekstrakcjaProgres.setVisible(True)

    def ekstrakcja_odwies(self):
        self.window.startEkstrakcji.setEnabled(True)
        self.window.wyszukiwanie.setEnabled(True)
       # self.window.ekstrakcjaProgres.setVisible(False)

    def ekstrakcja_sukces(self, liczba_klatek):
        self.ekstrakcja_odwies()
        fotki = len(os.listdir(sciezka_zdjecia))
        # self.aktualizuj_liczbe_zdjec() nie mam zielonego pojecia jak to sie tutaj znalazlo ani co to za metoda
        QMessageBox.information(
            self.window, 'Sukces', f'Pomyślnie zapisano {liczba_klatek} klatek w folderze ./work/zdjecia/')
        self.window.rekonstrukcjaLabel2.setText(
            f'{fotki} zdjęć')
        logging.info(
            f"Zakończono ekstrakcję klatek z filmu {Path(self.film.sciezka).name} ({liczba_klatek}) [{self.window.wyborRozdzielczosci.currentData()[0]}x{self.window.wyborRozdzielczosci.currentData()[1]}]")

    def ekstrakcja_blad(self, komunikat_bledu):
        self.ekstrakcja_odwies()
        QMessageBox.critical(self.window, 'Błąd',
                             f'Wystąpił błąd: {komunikat_bledu}')

    def start_extract(self):
        # walidacja
        if (self.film == None):
            QMessageBox.warning(self.window, 'Błąd',
                                'Proszę wybrać plik wideo!')
            return
        if not os.path.exists(self.film.sciezka):
            QMessageBox.warning(self.window, 'Błąd',
                                'Wybrany plik nie istnieje!')
            return

        docelowa_liczba_klatek = self.window.wybierzLiczbeKlatek.value()
        try:
            if docelowa_liczba_klatek <= 0:
                raise ValueError("Liczba klatek musi być dodatnia")
        except ValueError:
            QMessageBox.warning(self.window, 'Błąd',
                                'Proszę wprowadzić poprawną liczbę klatek!')
            return

        docelowa_rozdzielczosc = self.window.wyborRozdzielczosci.currentData()

        # zawiesi UI zeby nie wywolal uzytkownik pare razy
        self.window.startEkstrakcji.setEnabled(False)
        self.window.wyszukiwanie.setEnabled(False)
        self.window.ekstrakcjaProgres.setVisible(True)
        logging.info(
            f"Start ekstrakcji klatek z filmu {Path(self.film.sciezka).name} ({docelowa_liczba_klatek}) [{self.window.wyborRozdzielczosci.currentData()[0]}x{self.window.wyborRozdzielczosci.currentData()[1]}]")

        # nowy wontek
        self.window.extraction_thread = ExtractionThread(
            self.film,
            docelowa_liczba_klatek,
            docelowa_rozdzielczosc
        )
        self.window.extraction_thread.koniec.connect(self.ekstrakcja_sukces)
        self.window.extraction_thread.err.connect(self.ekstrakcja_blad)
        self.window.extraction_thread.log_signal.connect(self.log)
        self.window.extraction_thread.progres.connect(
            self.window.ekstrakcjaProgres.setValue)
        self.window.extraction_thread.start()

    def colmap_sukces(self, nazwa_modelu):
        self.window.startRekonstrukcji.setEnabled(True)
        QMessageBox.information(
            self.window, 'Sukces', f'Rekonstrukcja zakończona! Model zapisano jako {nazwa_modelu}')

    def colmap_blad(self, komunikat_bledu):
        self.window.startRekonstrukcji.setEnabled(True)
        QMessageBox.critical(
            self.window, 'Błąd', f'Wystąpił błąd podczas rekonstrukcji: {komunikat_bledu}')

    def start_colmap(self):
        nazwa_modelu = self.window.nazwaModelu.text().strip()
        opcje = self.window.wyborOpcji.currentData()
        if not nazwa_modelu:
            QMessageBox.warning(self.window, 'Błąd',
                                'Proszę podać nazwę modelu 3D!')
            return

        if not nazwa_modelu.endswith('.ply'):
            nazwa_modelu += '.ply'

        print("opcje:", opcje)
        print("nazwa:", nazwa_modelu)
        print("GPU:", self.window.czyGPU.isChecked())
        # Trzeba sprawdzic czy sa zdjecia
        if not os.path.exists(sciezka_zdjecia) or not os.listdir(sciezka_zdjecia):
            QMessageBox.warning(self.window, 'Błąd',
                                'Brak zdjęć! Najpierw wykonaj ekstrakcję.')
            return

        # Wyłączenie GUI na czas rekonstrukcji
        self.window.startRekonstrukcji.setEnabled(False)

        # colmap.py w osobnym wątku
        self.colmap_thread = ColmapThread(nazwa_modelu, self.window.wybierzLiczbeWatkow.value(), opcje, self.window.wymusRekonstrukcje.isChecked(), self.window.matchowanieCheckBox.isChecked(), self.window.czyGPU.isChecked())
        self.colmap_thread.koniec.connect(self.colmap_sukces)
        self.colmap_thread.err.connect(self.colmap_blad)
        self.colmap_thread.log_signal.connect(self.log)
        self.colmap_thread.start()

    def mesh_sukces(self, nazwa_modelu):
        self.window.startMeshowania.setEnabled(True)
        QMessageBox.information(
            self.window, 'Sukces', f'Siatka stworzona! Model zapisano jako {nazwa_modelu}')

    def mesh_blad(self, komunikat_bledu):
        self.window.startMeshowania.setEnabled(True)
        QMessageBox.critical(
            self.window, 'Błąd', f'Wystąpił błąd podczas tworzenia siatki: {komunikat_bledu}')

    def start_mesh(self):
        nazwa_modelu = self.window.nazwaModelu.text().strip()
        metoda = self.window.metodaWybor.currentData()
        if not nazwa_modelu:
            QMessageBox.warning(self.window, 'Błąd',
                                'Proszę podać nazwę modelu 3D!')
            return

        print("opcje:", metoda)
        print("nazwa:", nazwa_modelu)
        if not nazwa_modelu.endswith('.ply'):
            nazwa_modelu += '.ply'
        # Trzeba sprawdzic czy jest ten plik
        if not os.path.exists("./chmury/"+nazwa_modelu):
            QMessageBox.warning(self.window, 'Błąd',
                                'Wybrany model nie istnieje!.')
            return

        # Wyłączenie GUI na czas rekonstrukcji
        self.window.startMeshowania.setEnabled(False)

        # colmap.py w osobnym wątku
        self.mesh_thread = MeshingThread(nazwa_modelu, metoda)
        self.mesh_thread.koniec.connect(self.mesh_sukces)
        self.mesh_thread.err.connect(self.mesh_blad)
        self.mesh_thread.log_signal.connect(self.log)
        self.mesh_thread.start()

    def zapisz_ustawienia(self):
        #ograniczenia ustawień:
        with open(sciezka_ustawienia, "r") as f:
            data = yaml.safe_load(f)

        if "Options" not in data or not isinstance(data["Options"], list):
            raise ValueError("Niepoprawna struktura pliku options.yaml")

        options = data["Options"]

        #jesli by nie bylo jeszcze opcji uzytkownika
        if len(options) < 4:
            options.append({})

        #nadpisanie
        opcje = {"max_features": self.window.maxFeatures.value(), "num_nearest_neighbors": self.window.numNearestNeighbors.value(),
                 "num_checks": self.window.numChecks.value(), "ba_global_max_num_iterations": self.window.baGlobal.value(),
                 "level": self.window.level.value(), "threshold": 0.7,
                 "useVisData": 1, "sequence": self.window.sequence.value(),
                 "quad": self.window.quad.value(), "maxAngle": self.window.maxAngle.value(), "csize": self.window.csize.value(),
                 "cmvs_images_per_cluster": 20};

        options[3].update(opcje)

        with open(sciezka_ustawienia, "w") as f:
            yaml.safe_dump(data, f, sort_keys=False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    my_win = MyWindow()
    my_win.window.show()
    sys.exit(app.exec())
