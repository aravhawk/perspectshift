#include "perceptshift/image/image_view.hpp"
#include "perceptshift/image/pixel_format.hpp"
#include "perceptshift/image/preprocess_config.hpp"
#include "perceptshift/image/preprocessor.hpp"
#include "perceptshift/image/tensor_buffer.hpp"
#include "perceptshift/version.hpp"

#include <CLI/CLI.hpp>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <nlohmann/json.hpp>
#include <vector>

namespace {

std::vector<std::uint8_t> read_bytes(const std::filesystem::path& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    throw std::runtime_error("unable to open " + path.string());
  }
  return std::vector<std::uint8_t>(std::istreambuf_iterator<char>(in),
                                   std::istreambuf_iterator<char>());
}

} // namespace

int main(int argc, char** argv) {
  CLI::App app{"PerceptShift native preprocess worker (canonical production path)"};
  std::string image_path;
  std::string contract_path;
  std::string output_path;
  std::string pixel_format = "rgb8";
  std::size_t width = 0;
  std::size_t height = 0;
  std::size_t stride_bytes = 0;
  bool version = false;
  app.add_flag("--version", version, "Print version");
  app.add_option("--image", image_path, "Raw pixel file");
  app.add_option("--contract", contract_path, "Preprocess contract JSON");
  app.add_option("--output", output_path, "Output float32 tensor file");
  app.add_option("--pixel-format", pixel_format, "Source pixel format");
  app.add_option("--width", width, "Source width");
  app.add_option("--height", height, "Source height");
  app.add_option("--stride-bytes", stride_bytes, "Source stride (0 = tightly packed)");
  CLI11_PARSE(app, argc, argv);

  if (version) {
    std::cout << perceptshift::kVersionString << "\n";
    return 0;
  }
  if (image_path.empty() || contract_path.empty() || output_path.empty() || width == 0 ||
      height == 0) {
    std::cerr << nlohmann::json(
                     {{"status", "error"},
                      {"code", "CONFIG_INVALID"},
                      {"message", "missing --image/--contract/--output/--width/--height"}})
              << "\n";
    return 2;
  }

  try {
    auto contract = nlohmann::json::parse(std::ifstream(contract_path));
    auto cfg = perceptshift::image::preprocess_config_from_json(contract);
    if (!cfg) {
      std::cerr << nlohmann::json({{"status", "error"},
                                   {"code", "CONFIG_INVALID"},
                                   {"message", cfg.error().message}})
                << "\n";
      return 2;
    }
    perceptshift::image::PixelFormat fmt{};
    if (!perceptshift::image::parse_pixel_format(pixel_format, fmt)) {
      std::cerr << nlohmann::json({{"status", "error"},
                                   {"code", "INPUT_UNSUPPORTED"},
                                   {"message", "unsupported pixel format: " + pixel_format}})
                << "\n";
      return 2;
    }
    auto bytes = read_bytes(image_path);
    if (stride_bytes == 0) {
      const std::size_t channels = (fmt == perceptshift::image::PixelFormat::Mono8)   ? 1
                                   : (fmt == perceptshift::image::PixelFormat::Rgba8 ||
                                      fmt == perceptshift::image::PixelFormat::Bgra8)
                                       ? 4
                                       : 3;
      stride_bytes = width * channels;
    }
    if (bytes.size() < stride_bytes * height) {
      std::cerr << nlohmann::json({{"status", "error"},
                                   {"code", "INPUT_UNSUPPORTED"},
                                   {"message", "raw image smaller than width*height*stride"}})
                << "\n";
      return 2;
    }
    perceptshift::image::ImageView view;
    view.data = bytes.data();
    view.width = width;
    view.height = height;
    view.stride_bytes = stride_bytes;
    view.format = fmt;

    perceptshift::image::TensorBuffer buf;
    auto meta = perceptshift::image::preprocess_to_float_tensor(view, cfg.value(), buf);
    if (!meta) {
      std::cerr << nlohmann::json({{"status", "error"},
                                   {"code", "PREPROCESS_FAILED"},
                                   {"message", meta.error().message}})
                << "\n";
      return 2;
    }
    std::ofstream out(output_path, std::ios::binary);
    if (!out) {
      throw std::runtime_error("unable to write " + output_path);
    }
    out.write(reinterpret_cast<const char*>(buf.data()),
              static_cast<std::streamsize>(buf.size() * sizeof(float)));
    nlohmann::json report{
        {"status", "ok"},
        {"document_type", "perceptshift.preprocess_worker_result"},
        {"schema_version", "1.0"},
        {"output_path", output_path},
        {"float_count", buf.size()},
        {"impl", meta.value().impl == perceptshift::image::PreprocessImplUsed::Neon ? "neon"
                                                                                    : "scalar"},
        {"contract", perceptshift::image::preprocess_config_to_json(cfg.value())},
    };
    std::cout << report.dump() << "\n";
    return 0;
  } catch (const std::exception& ex) {
    std::cerr << nlohmann::json(
                     {{"status", "error"}, {"code", "CONFIG_INVALID"}, {"message", ex.what()}})
              << "\n";
    return 2;
  }
}
