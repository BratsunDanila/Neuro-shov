from __future__ import annotations

import threading
from collections import Counter
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk
import torch
from ultralytics import YOLO
import yaml


APP_TITLE = "Тестирование сегментации дефектов сварки"
PREVIEW_SIZE = (720, 520)
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
CLASS_TRANSLATIONS = {
    "Bad Welding": "Плохой шов",
    "Crack": "Трещина",
    "Excess Reinforcement": "Избыточное усиление",
    "Good Welding": "Хороший шов",
    "Porosity": "Пористость",
    "Spatters": "Брызги",
}
LABEL_COLORS = [
    "#c0392b",
    "#d35400",
    "#2980b9",
    "#27ae60",
    "#16a085",
    "#8e44ad",
]


def default_device() -> str:
    return "0" if torch.cuda.is_available() else "cpu"


def available_devices() -> list[str]:
    return ["0", "cpu"] if torch.cuda.is_available() else ["cpu"]


def find_default_weights() -> Path | None:
    preferred = [
        Path("runs") / "welding-seg-yolo26s-clean-ft40" / "weights" / "best.pt",
        Path("runs") / "welding-seg-yolo26s-e100" / "weights" / "best.pt",
    ]
    for candidate in preferred:
        if candidate.exists():
            return candidate.resolve()

    runs_dir = Path("runs")
    candidates = sorted(
        runs_dir.glob("**/weights/best.pt"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0].resolve()
    return None


def find_args_yaml_for_weights(weights_path: Path) -> Path | None:
    if weights_path.name not in {"best.pt", "last.pt"}:
        return None
    candidate = weights_path.parent.parent / "args.yaml"
    return candidate if candidate.exists() else None


def load_training_imgsz(weights_path: Path) -> int | None:
    args_path = find_args_yaml_for_weights(weights_path)
    if args_path is None:
        return None
    try:
        with args_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except Exception:
        return None

    imgsz = data.get("imgsz")
    return int(imgsz) if isinstance(imgsz, int | float) else None


def resize_for_preview(image: Image.Image, max_size: tuple[int, int]) -> Image.Image:
    preview = image.copy()
    preview.thumbnail(max_size, Image.Resampling.LANCZOS)
    return preview


def translate_class_name(name: str) -> str:
    return CLASS_TRANSLATIONS.get(name, name)


def translated_names(names: dict[int, str]) -> dict[int, str]:
    return {idx: translate_class_name(name) for idx, name in names.items()}


def load_label_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_candidates = [
        "arial.ttf",
        "segoeui.ttf",
        "tahoma.ttf",
    ]
    for candidate in font_candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_labels_without_boxes(base_image: Image.Image, result) -> Image.Image:
    if result.boxes is None or len(result.boxes) == 0:
        return base_image

    image = base_image.convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    font = load_label_font(20)

    boxes_xyxy = result.boxes.xyxy.detach().cpu().tolist()
    class_ids = result.boxes.cls.detach().cpu().tolist()
    confidences = result.boxes.conf.detach().cpu().tolist()

    for xyxy, class_id, confidence in zip(boxes_xyxy, class_ids, confidences):
        class_index = int(class_id)
        class_name = result.names[class_index]
        label = f"{class_name} {confidence:.2f}"
        color = LABEL_COLORS[class_index % len(LABEL_COLORS)]

        x1, y1, x2, _ = xyxy
        anchor_x = max(6, int(x1))
        anchor_y = max(6, int(y1) - 30)

        bbox = draw.textbbox((anchor_x, anchor_y), label, font=font)
        bg_rect = (
            bbox[0] - 8,
            bbox[1] - 4,
            bbox[2] + 8,
            bbox[3] + 4,
        )
        draw.rounded_rectangle(
            bg_rect, radius=8, fill=(16, 20, 24, 210), outline=color, width=2
        )
        draw.text((anchor_x, anchor_y), label, font=font, fill=(255, 255, 255, 255))

    return image.convert("RGB")


def render_result_summary(result) -> str:
    lines: list[str] = []
    detections = 0 if result.boxes is None else len(result.boxes)
    lines.append(f"Найдено объектов: {detections}")

    if detections == 0 or result.boxes is None:
        lines.append("Объекты не найдены.")
        return "\n".join(lines)

    class_ids = result.boxes.cls.tolist()
    confidences = result.boxes.conf.tolist()
    counts = Counter(
        translate_class_name(result.names[int(class_id)]) for class_id in class_ids
    )

    lines.append("Количество по классам:")
    for class_name, count in counts.most_common():
        lines.append(f"  {class_name}: {count}")

    lines.append("")
    lines.append("Обнаружения:")
    for idx, (class_id, confidence) in enumerate(zip(class_ids, confidences), start=1):
        class_name = translate_class_name(result.names[int(class_id)])
        lines.append(f"  {idx}. {class_name} ({confidence:.3f})")

    return "\n".join(lines)


class SegmentationTesterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1480x920")
        self.root.minsize(1240, 820)

        self.model: YOLO | None = None
        self.loaded_model_path: Path | None = None
        self.current_result_image: Image.Image | None = None
        self.original_preview_ref: ImageTk.PhotoImage | None = None
        self.prediction_preview_ref: ImageTk.PhotoImage | None = None
        self.is_running = False

        self.weights_var = tk.StringVar(value=str(find_default_weights() or ""))
        self.image_var = tk.StringVar()
        self.device_var = tk.StringVar(value=default_device())
        self.conf_var = tk.DoubleVar(value=0.25)
        self.imgsz_var = tk.IntVar(value=640)
        self.status_var = tk.StringVar(
            value="Готово. Выберите изображение и запустите сегментацию."
        )

        self._configure_style()
        self._build_layout()
        self._sync_ui_with_weights()

    def _configure_style(self) -> None:
        self.root.configure(bg="#101418")
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            ".", background="#101418", foreground="#f2f5f7", fieldbackground="#182028"
        )
        style.configure("TFrame", background="#101418")
        style.configure(
            "TLabelframe", background="#101418", foreground="#f2f5f7", borderwidth=1
        )
        style.configure("TLabelframe.Label", background="#101418", foreground="#f2f5f7")
        style.configure("TLabel", background="#101418", foreground="#f2f5f7")
        style.configure(
            "TButton",
            background="#1f8a70",
            foreground="#ffffff",
            padding=8,
            borderwidth=0,
        )
        style.map(
            "TButton", background=[("active", "#26a485"), ("disabled", "#5a6772")]
        )
        style.configure("Secondary.TButton", background="#34414d")
        style.map(
            "Secondary.TButton",
            background=[("active", "#455462"), ("disabled", "#5a6772")],
        )
        style.configure("TEntry", padding=6)
        style.configure("TCombobox", padding=4)
        style.configure("TScale", background="#101418")

    def _build_layout(self) -> None:
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        controls = ttk.LabelFrame(main, text="Параметры распознавания", padding=14)
        controls.pack(fill="x")

        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(4, weight=1)

        ttk.Label(controls, text="Веса модели").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=6
        )
        ttk.Entry(controls, textvariable=self.weights_var).grid(
            row=0, column=1, columnspan=3, sticky="ew", pady=6
        )
        ttk.Button(
            controls, text="Обзор", command=self.pick_weights, style="Secondary.TButton"
        ).grid(row=0, column=4, sticky="ew", padx=(8, 0), pady=6)

        ttk.Label(controls, text="Изображение").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=6
        )
        ttk.Entry(controls, textvariable=self.image_var).grid(
            row=1, column=1, columnspan=3, sticky="ew", pady=6
        )
        ttk.Button(
            controls, text="Обзор", command=self.pick_image, style="Secondary.TButton"
        ).grid(row=1, column=4, sticky="ew", padx=(8, 0), pady=6)

        ttk.Label(controls, text="Порог confidence").grid(
            row=2, column=0, sticky="w", padx=(0, 8), pady=6
        )
        ttk.Scale(controls, from_=0.05, to=0.95, variable=self.conf_var).grid(
            row=2, column=1, sticky="ew", pady=6
        )
        ttk.Label(controls, textvariable=tk.StringVar(value="")).grid_forget()
        self.conf_value_label = ttk.Label(controls, text=self._format_conf())
        self.conf_value_label.grid(row=2, column=2, sticky="w", padx=(8, 0), pady=6)
        self.root.after(100, self._refresh_conf_label)

        ttk.Label(controls, text="Размер изображения").grid(
            row=2, column=3, sticky="e", padx=(16, 8), pady=6
        )
        ttk.Combobox(
            controls,
            textvariable=self.imgsz_var,
            values=[512, 640, 768, 960, 1024],
            state="readonly",
            width=10,
        ).grid(row=2, column=4, sticky="ew", pady=6)

        ttk.Label(controls, text="Устройство").grid(
            row=3, column=0, sticky="w", padx=(0, 8), pady=6
        )
        self.device_combo = ttk.Combobox(
            controls,
            textvariable=self.device_var,
            values=available_devices(),
            state="readonly",
            width=10,
        )
        self.device_combo.grid(row=3, column=1, sticky="w", pady=6)

        buttons = ttk.Frame(controls)
        buttons.grid(row=3, column=3, columnspan=2, sticky="e", pady=6)
        self.run_button = ttk.Button(
            buttons, text="Запустить сегментацию", command=self.run_inference
        )
        self.run_button.pack(side="left", padx=(0, 8))
        self.save_button = ttk.Button(
            buttons,
            text="Сохранить результат",
            command=self.save_result,
            style="Secondary.TButton",
        )
        self.save_button.pack(side="left")

        status = ttk.Label(main, textvariable=self.status_var, anchor="w")
        status.pack(fill="x", pady=(10, 10))

        previews = ttk.Frame(main)
        previews.pack(fill="both", expand=True)
        previews.columnconfigure(0, weight=1)
        previews.columnconfigure(1, weight=1)
        previews.rowconfigure(0, weight=1)

        self.original_panel = self._create_preview_panel(
            previews, "Исходное изображение"
        )
        self.original_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.prediction_panel = self._create_preview_panel(
            previews, "Результат сегментации"
        )
        self.prediction_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        bottom = ttk.Frame(main)
        bottom.pack(fill="both", expand=False, pady=(12, 0))

        details_frame = ttk.LabelFrame(
            bottom, text="Сводка по обнаружениям", padding=12
        )
        details_frame.pack(fill="both", expand=True)
        self.details_text = scrolledtext.ScrolledText(
            details_frame,
            height=10,
            wrap="word",
            bg="#182028",
            fg="#f2f5f7",
            insertbackground="#f2f5f7",
            relief="flat",
            font=("Consolas", 10),
        )
        self.details_text.pack(fill="both", expand=True)
        self.details_text.insert(
            "1.0", "Откройте изображение, чтобы увидеть результаты распознавания."
        )
        self.details_text.configure(state="disabled")

    def _create_preview_panel(self, parent: ttk.Frame, title: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=title, padding=10)
        label = tk.Label(
            frame,
            text="Изображение не загружено",
            bg="#182028",
            fg="#c9d3dc",
            font=("Segoe UI", 12),
            relief="flat",
        )
        label.pack(fill="both", expand=True)
        frame.image_label = label
        return frame

    def _format_conf(self) -> str:
        return f"{self.conf_var.get():.2f}"

    def _refresh_conf_label(self) -> None:
        self.conf_value_label.configure(text=self._format_conf())
        self.root.after(100, self._refresh_conf_label)

    def pick_weights(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите веса YOLO",
            filetypes=[("Файлы весов PyTorch", "*.pt"), ("Все файлы", "*.*")],
        )
        if path:
            self.weights_var.set(path)
            self._sync_ui_with_weights()

    def _sync_ui_with_weights(self) -> None:
        valid_devices = available_devices()
        self.device_combo.configure(values=valid_devices)
        if self.device_var.get() not in valid_devices:
            self.device_var.set(valid_devices[0])

        weights_text = self.weights_var.get().strip()
        if not weights_text:
            if not torch.cuda.is_available():
                self.status_var.set("CUDA недоступна. Используется CPU.")
            return

        weights_path = Path(weights_text)
        trained_imgsz = load_training_imgsz(weights_path)
        if trained_imgsz:
            self.imgsz_var.set(trained_imgsz)
            device_hint = (
                " CUDA недоступна. Используется CPU."
                if not torch.cuda.is_available()
                else ""
            )
            self.status_var.set(
                f"Подхвачены параметры модели. Рекомендуемый imgsz: {trained_imgsz}.{device_hint}"
            )

    def pick_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите изображение для проверки",
            filetypes=[
                ("Файлы изображений", "*.jpg *.jpeg *.png *.bmp *.webp"),
                ("Все файлы", "*.*"),
            ],
        )
        if not path:
            return

        self.image_var.set(path)
        self._show_image_preview(
            Path(path), self.original_panel, store_attr="original_preview_ref"
        )
        self._set_details(
            "Изображение выбрано. Нажмите «Запустить сегментацию», чтобы проверить модель."
        )
        self.status_var.set("Изображение загружено. Готово к распознаванию.")

    def _show_image_preview(
        self, image_path: Path, panel: ttk.LabelFrame, store_attr: str
    ) -> None:
        image = Image.open(image_path).convert("RGB")
        self._show_pil_image(image, panel, store_attr)

    def _show_pil_image(
        self, image: Image.Image, panel: ttk.LabelFrame, store_attr: str
    ) -> None:
        preview = resize_for_preview(image, PREVIEW_SIZE)
        photo = ImageTk.PhotoImage(preview)
        label = panel.image_label
        label.configure(image=photo, text="")
        setattr(self, store_attr, photo)

    def _set_details(self, text: str) -> None:
        self.details_text.configure(state="normal")
        self.details_text.delete("1.0", "end")
        self.details_text.insert("1.0", text)
        self.details_text.configure(state="disabled")

    def _load_model_if_needed(self, weights_path: Path) -> YOLO:
        if self.model is None or self.loaded_model_path != weights_path:
            self.model = YOLO(str(weights_path))
            self.loaded_model_path = weights_path
        return self.model

    def run_inference(self) -> None:
        if self.is_running:
            return

        weights_path = Path(self.weights_var.get())
        image_path = Path(self.image_var.get())

        if not weights_path.exists():
            messagebox.showerror(
                "Файл весов не найден",
                "Выберите корректный файл `.pt` перед запуском распознавания.",
            )
            return
        if (
            not image_path.exists()
            or image_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES
        ):
            messagebox.showerror(
                "Файл изображения не найден",
                "Выберите корректное изображение перед запуском распознавания.",
            )
            return

        self.is_running = True
        self.run_button.configure(state="disabled")
        self.status_var.set("Выполняется сегментация...")
        self._set_details("Идёт распознавание...")

        thread = threading.Thread(
            target=self._run_inference_worker,
            args=(
                weights_path.resolve(),
                image_path.resolve(),
                self.conf_var.get(),
                self.imgsz_var.get(),
                self.device_var.get(),
            ),
            daemon=True,
        )
        thread.start()

    def _run_inference_worker(
        self, weights_path: Path, image_path: Path, conf: float, imgsz: int, device: str
    ) -> None:
        try:
            model = self._load_model_if_needed(weights_path)
            results = model.predict(
                source=str(image_path),
                conf=conf,
                imgsz=imgsz,
                device=device,
                verbose=False,
            )
            result = results[0]
            result.names = translated_names(result.names)
            plotted = Image.fromarray(
                result.plot(boxes=False, labels=False, masks=True, conf=False)
            )
            plotted = draw_labels_without_boxes(plotted, result)
            summary = render_result_summary(result)
            self.root.after(0, self._on_inference_success, image_path, plotted, summary)
        except Exception as exc:  # pragma: no cover - defensive UI path
            self.root.after(0, self._on_inference_error, str(exc))

    def _on_inference_success(
        self, image_path: Path, result_image: Image.Image, summary: str
    ) -> None:
        self.current_result_image = result_image
        self._show_pil_image(
            result_image, self.prediction_panel, "prediction_preview_ref"
        )
        if not self.image_var.get():
            self.image_var.set(str(image_path))
        self._set_details(summary)
        self.status_var.set("Сегментация завершена.")
        self.run_button.configure(state="normal")
        self.is_running = False

    def _on_inference_error(self, error_message: str) -> None:
        self.status_var.set("Ошибка распознавания.")
        self.run_button.configure(state="normal")
        self.is_running = False
        self._set_details(error_message)
        messagebox.showerror("Ошибка распознавания", error_message)

    def save_result(self) -> None:
        if self.current_result_image is None:
            messagebox.showinfo(
                "Нечего сохранять",
                "Сначала запустите распознавание, чтобы появился результат.",
            )
            return

        image_path = (
            Path(self.image_var.get())
            if self.image_var.get()
            else Path("prediction.png")
        )
        default_name = f"{image_path.stem}_segmented.png"
        target = filedialog.asksaveasfilename(
            title="Сохранить размеченное изображение",
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[
                ("PNG изображение", "*.png"),
                ("JPEG изображение", "*.jpg"),
                ("Все файлы", "*.*"),
            ],
        )
        if not target:
            return

        self.current_result_image.save(target)
        self.status_var.set(f"Результат сохранён: {target}")


def main() -> None:
    root = tk.Tk()
    app = SegmentationTesterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
