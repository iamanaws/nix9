#include <atomic>
#include "nix/store/filetransfer.hh"
#include "nix/util/callback.hh"
#include "nix/util/file-descriptor.hh"
#include "nix/util/signals.hh"

#include <fcntl.h>
#include <unistd.h>

extern "C" const char *__n9_errstr_last(int *);

namespace nix {

const unsigned int RETRY_TIME_MS_DEFAULT = 250;

std::filesystem::path FileTransferSettings::getDefaultSSLCertFile() { return ""; }
FileTransferSettings::FileTransferSettings() = default;
FileTransferSettings fileTransferSettings;

template<typename... Args>
FileTransferError::FileTransferError(
    FileTransfer::Error error, std::optional<std::string> response, const Args &... args)
    : CloneableError(args...), error(error), response(std::move(response)) {}

[[noreturn]] static void transferError(const FileTransferRequest &request)
{
    std::string message = __n9_errstr_last(nullptr);
    auto error = FileTransfer::Misc;
    if (message.starts_with("404 ")) error = FileTransfer::NotFound;
    else if (message.starts_with("403 ")) error = FileTransfer::Forbidden;
    else if (message.starts_with("408 ") || message.starts_with("429 ") || message.starts_with("5"))
        error = FileTransfer::Transient;
    throw FileTransferError(error, std::nullopt, "webfs request for '%s' failed: %s", request.uri, message);
}

static FileTransferResult transfer(const FileTransferRequest &request, Sink *sink = nullptr)
{
    if (request.method != HttpMethod::Get && request.method != HttpMethod::Head)
        throw Error("webfs transfers are read-only");
    if (request.data || request.dataCallback || request.tlsCert || request.tlsKey
        || request.usernameAuth || !request.headers.empty())
        throw Error("webfs transfers do not support upload data, callbacks, client credentials or custom headers");
    auto scheme = request.uri.parsed().scheme;
    if (scheme != "http" && scheme != "https")
        throw Error("webfs transfers require an HTTP or HTTPS URL");

    AutoCloseFD control(open("/mnt/web/clone", O_RDWR | O_CLOEXEC));
    if (!control)
        throw Error("cannot open /mnt/web/clone; mount webfs before using HTTP caches");
    char buffer[65536];
    auto count = ::read(control.get(), buffer, 32);
    if (count < 0) transferError(request);
    auto id = chomp(std::string(buffer, count));
    if (id.empty() || id.find_first_not_of("0123456789") != std::string::npos)
        throw Error("webfs returned an invalid connection number");
    auto connection = "/mnt/web/" + id;
    auto command = [&](const std::string &text) {
        auto written = ::write(control.get(), text.data(), text.size());
        if (written < 0) transferError(request);
        if ((size_t) written != text.size())
            throw FileTransferError(FileTransfer::Misc, std::nullopt, "short write to webfs control file");
    };
    command("url " + request.uri.to_string());
    if (request.method == HttpMethod::Head) command("request HEAD");
    AutoCloseFD body(open((connection + "/body").c_str(), O_RDONLY | O_CLOEXEC));
    if (!body) transferError(request);

    FileTransferResult result;
    result.urls.push_back(request.uri.to_string());
    while (true) {
        checkInterrupt();
        count = ::read(body.get(), buffer, sizeof(buffer));
        if (count < 0) {
            if (errno == EINTR) { checkInterrupt(); continue; }
            transferError(request);
        }
        if (count == 0) break;
        std::string_view chunk(buffer, count);
        if (sink) (*sink)(chunk);
        else result.data.append(chunk);
        result.bodySize += count;
    }
    return result;
}

struct WebFileTransfer : FileTransfer
{
    ItemHandle enqueueFileTransfer(const FileTransferRequest &request, Callback<FileTransferResult> callback) override
    {
        try { callback(transfer(request)); }
        catch (...) { callback.rethrow(); }
        return ItemHandle({});
    }

    void unpauseTransfer(ItemHandle) override { throw nix::Error("webfs transfers cannot be paused"); }
};

ref<FileTransfer> getFileTransfer() { return make_ref<WebFileTransfer>(); }
ref<FileTransfer> makeFileTransfer(const FileTransferSettings &) { return getFileTransfer(); }

std::future<FileTransferResult> FileTransfer::enqueueFileTransfer(const FileTransferRequest &request)
{
    auto promise = std::make_shared<std::promise<FileTransferResult>>();
    auto future = promise->get_future();
    enqueueFileTransfer(request, {[promise](std::future<FileTransferResult> result) {
        try { promise->set_value(result.get()); }
        catch (...) { promise->set_exception(std::current_exception()); }
    }});
    return future;
}

FileTransferResult FileTransfer::download(const FileTransferRequest &request) { return enqueueFileTransfer(request).get(); }
FileTransferResult FileTransfer::upload(const FileTransferRequest &request) { return enqueueFileTransfer(request).get(); }
FileTransferResult FileTransfer::deleteResource(const FileTransferRequest &request) { return enqueueFileTransfer(request).get(); }

void FileTransfer::download(FileTransferRequest &&request, Sink &sink, std::function<void(FileTransferResult)> callback)
{
    // Read on the caller's thread: a coroutine sink cannot move between threads.
    auto result = transfer(request, &sink);
    if (callback) callback(std::move(result));
}

} // namespace nix
