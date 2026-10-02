#include "nix/util/signature/local-keys.hh"
#include <fstream>
#include <iostream>
#include <iterator>

static void require(bool condition) {
    if (!condition) throw std::runtime_error("signature check failed");
}

void checkKeys(const char *fixture, const char *input) {
    std::ifstream keys(fixture), data(input, std::ios::binary);
    if (!keys || !data) throw std::runtime_error("missing signing fixture");
    std::string secret, publicKey, emptySignature, signature;
    std::getline(keys, secret);
    std::getline(keys, publicKey);
    std::getline(keys, emptySignature);
    std::getline(keys, signature);
    std::string message((std::istreambuf_iterator<char>(data)), {});
    nix::SecretKey key(secret);
    nix::PublicKey pub(publicKey);
    require(key.to_string() == secret && key.toPublicKey().to_string() == publicKey);
    require(key.signDetached("").to_string() == emptySignature);
    require(pub.verifyDetached("", nix::Signature::parse(emptySignature)));
    auto sig = nix::Signature::parse(signature);
    require(key.signDetached(message).to_string() == signature);
    require(pub.verifyDetached(message, sig));
    require(!pub.verifyDetached(message + "x", sig));
    sig.sig[0] ^= 1;
    require(!pub.verifyDetached(message, sig));
    sig = nix::Signature::parse(signature);
    sig.keyName = "wrong-name";
    require(!pub.verifyDetached(message, sig));
    sig = nix::Signature::parse(signature);
    sig.sig.pop_back();
    bool rejected = false;
    try { pub.verifyDetached(message, sig); }
    catch (const nix::Error &) { rejected = true; }
    require(rejected);
    auto generated = nix::SecretKey::generate("guest");
    auto other = nix::SecretKey::generate("guest");
    require(generated.toPublicKey().to_string() != other.toPublicKey().to_string());
    auto signedMessage = generated.signDetached(message);
    require(!other.toPublicKey().verifyDetached(message, signedMessage));
    // Return only the public key and signature for independent host verification.
    std::cout << "PUBLIC " << generated.toPublicKey().to_string() << '\n'
              << "SIGNATURE " << signedMessage.to_string() << '\n';
}
