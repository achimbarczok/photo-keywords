"""ConfigLoader zum Laden und Validieren der YAML-Konfigurationsdatei."""

from __future__ import annotations

import yaml

from lightroom_ollama_keywords.errors import ConfigError
from lightroom_ollama_keywords.models import (
    Config,
    FotoKategorie,
    KategorieConfig,
    KlassifikationsConfig,
    StandortConfig,
    ValidierungsConfig,
)


_REQUIRED_PARAMS = ("catalog_path", "model_name")

_DEFAULTS = {
    "ollama_endpoint": "http://localhost:11434",
    "batch_size": 50,
    "prompt_template": (
        "Describe this image with descriptive keywords. "
        "Return only a comma-separated list of keywords."
    ),
    "tracking_db_path": "./tracking.db",
    "log_file_path": "./keyword_generator.log",
    "exiftool_path": None,
    "benchmark_models": [],
    "benchmark_output_csv": "./benchmark_results.csv",
}

# Maps German display names (YAML keys) to FotoKategorie enum members
_KATEGORIE_NAME_LOOKUP: dict[str, FotoKategorie] = {
    k.value: k for k in FotoKategorie
}


class ConfigLoader:
    """Lädt und validiert eine YAML-Konfigurationsdatei."""

    def load(self, config_path: str) -> Config:
        """Lädt die Konfiguration aus einer YAML-Datei.

        Raises:
            ConfigError: Bei fehlender Datei oder fehlenden Pflichtparametern.
        """
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            raise ConfigError(f"Konfigurationsdatei nicht gefunden: {config_path}")

        for param in _REQUIRED_PARAMS:
            if param not in data:
                raise ConfigError(f"Pflichtparameter fehlt: {param}")

        return Config(
            catalog_path=data["catalog_path"],
            model_name=data["model_name"],
            ollama_endpoint=data.get("ollama_endpoint", _DEFAULTS["ollama_endpoint"]),
            batch_size=data.get("batch_size", _DEFAULTS["batch_size"]),
            prompt_template=data.get("prompt_template", _DEFAULTS["prompt_template"]),
            tracking_db_path=data.get("tracking_db_path", _DEFAULTS["tracking_db_path"]),
            log_file_path=data.get("log_file_path", _DEFAULTS["log_file_path"]),
            exiftool_path=data.get("exiftool_path", _DEFAULTS["exiftool_path"]),
            benchmark_models=data.get("benchmark_models", _DEFAULTS["benchmark_models"]),
            benchmark_output_csv=data.get(
                "benchmark_output_csv", _DEFAULTS["benchmark_output_csv"]
            ),
            klassifikation=self._parse_classification(data.get("classification")),
            validierung=self._parse_validation(data.get("validation")),
            standort=self._parse_standort(data.get("location")),
        )

    def _parse_classification(
        self, classification_data: dict | None
    ) -> KlassifikationsConfig | None:
        """Parst den optionalen 'classification'-Abschnitt aus der YAML-Konfiguration.

        Args:
            classification_data: Der 'classification'-Abschnitt oder None.

        Returns:
            KlassifikationsConfig oder None wenn deaktiviert.

        Raises:
            ConfigError: Wenn eine Kategorie keinen Prompt hat.
        """
        if classification_data is None:
            return None

        modell = classification_data.get("model", "")
        prompt = classification_data.get("prompt", "")
        basis_prompt = classification_data.get("base_prompt", "")
        categories_data = classification_data.get("categories", {})

        kategorien: dict[FotoKategorie, KategorieConfig] = {}
        for name, cat_config in categories_data.items():
            foto_kategorie = _KATEGORIE_NAME_LOOKUP.get(name)
            if foto_kategorie is None:
                raise ConfigError(
                    f"Unbekannte Kategorie in classification.categories: {name}"
                )

            if cat_config is None or "prompt" not in cat_config:
                raise ConfigError(
                    f"Kategorie '{name}' hat keinen Prompt in classification.categories"
                )

            kategorien[foto_kategorie] = KategorieConfig(
                prompt=cat_config["prompt"],
                modell=cat_config.get("model"),
            )

        return KlassifikationsConfig(
            modell=modell,
            prompt=prompt,
            kategorien=kategorien,
            basis_prompt=basis_prompt,
        )

    def _parse_validation(
        self, validation_data: dict | None
    ) -> ValidierungsConfig:
        """Parst den optionalen 'validation'-Abschnitt aus der YAML-Konfiguration.

        Args:
            validation_data: Der 'validation'-Abschnitt oder None.

        Returns:
            ValidierungsConfig mit Standardwerten wenn validation_data None ist.
        """
        if validation_data is None:
            return ValidierungsConfig()

        defaults = ValidierungsConfig()
        return ValidierungsConfig(
            max_retries=validation_data.get("max_retries", defaults.max_retries),
            wortanzahl_schwellenwert=validation_data.get(
                "word_count_threshold", defaults.wortanzahl_schwellenwert
            ),
            einzeleintrag_schwellenwert=validation_data.get(
                "single_entry_threshold", defaults.einzeleintrag_schwellenwert
            ),
            retry_prompt=validation_data.get("retry_prompt", defaults.retry_prompt),
        )

    def _parse_standort(self, location_data: dict | None) -> StandortConfig:
        """Parst den optionalen 'location'-Abschnitt aus der YAML-Konfiguration.

        Args:
            location_data: Der 'location'-Abschnitt oder None.

        Returns:
            StandortConfig mit enabled=False wenn location_data None ist.
        """
        if location_data is None:
            return StandortConfig(enabled=False)
        return StandortConfig(enabled=location_data.get("enabled", False))
