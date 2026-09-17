/** THIS IS AN AUTOMATICALLY GENERATED FILE.  DO NOT MODIFY
 * BY HAND!!
 *
 * Generated for control_messages package
 **/

#include <lcm/lcm_coretypes.h>

#ifndef __control_messages_float64_hpp__
#define __control_messages_float64_hpp__

namespace control_messages
{

/// float64 type wrapper (maps to C++ double)
class float64
{
    public:
        double value;

    public:
        float64() : value(0.0) {}
        float64(double v) : value(v) {}
        float64(const float64& other) : value(other.value) {}
        
        operator double() const { return value; }
        float64& operator=(double v) { value = v; return *this; }
        float64& operator=(const float64& other) { value = other.value; return *this; }

        /**
         * Encode a message into binary form.
         */
        inline int encode(void *buf, int offset, int maxlen) const;

        /**
         * Check how many bytes are required to encode this message.
         */
        inline int getEncodedSize() const;

        /**
         * Decode a message from binary form into this instance.
         */
        inline int decode(const void *buf, int offset, int maxlen);

        /**
         * Retrieve the 64-bit fingerprint identifying the structure of the message.
         */
        inline static int64_t getHash();

        /**
         * Returns "float64"
         */
        inline static const char* getTypeName();

        // LCM support functions. Users should not call these
        inline int _encodeNoHash(void *buf, int offset, int maxlen) const;
        inline int _getEncodedSizeNoHash() const;
        inline int _decodeNoHash(const void *buf, int offset, int maxlen);
        inline static uint64_t _computeHash(const __lcm_hash_ptr *p);
};

int float64::encode(void *buf, int offset, int maxlen) const
{
    int pos = 0, tlen;
    int64_t hash = (int64_t)getHash();

    tlen = __int64_t_encode_array(buf, offset + pos, maxlen - pos, &hash, 1);
    if(tlen < 0) return tlen; else pos += tlen;

    tlen = this->_encodeNoHash(buf, offset + pos, maxlen - pos);
    if (tlen < 0) return tlen; else pos += tlen;

    return pos;
}

int float64::decode(const void *buf, int offset, int maxlen)
{
    int pos = 0, thislen;

    int64_t msg_hash;
    thislen = __int64_t_decode_array(buf, offset + pos, maxlen - pos, &msg_hash, 1);
    if (thislen < 0) return thislen; else pos += thislen;
    if (msg_hash != getHash()) return -1;

    thislen = this->_decodeNoHash(buf, offset + pos, maxlen - pos);
    if (thislen < 0) return thislen; else pos += thislen;

    return pos;
}

int float64::getEncodedSize() const
{
    return 8 + _getEncodedSizeNoHash();
}

int64_t float64::getHash()
{
    static int64_t hash = _computeHash(NULL);
    return hash;
}

const char* float64::getTypeName()
{
    return "float64";
}

int float64::_encodeNoHash(void *buf, int offset, int maxlen) const
{
    int pos = 0, tlen;

    tlen = __double_encode_array(buf, offset + pos, maxlen - pos, &this->value, 1);
    if(tlen < 0) return tlen; else pos += tlen;

    return pos;
}

int float64::_decodeNoHash(const void *buf, int offset, int maxlen)
{
    int pos = 0, tlen;

    tlen = __double_decode_array(buf, offset + pos, maxlen - pos, &this->value, 1);
    if(tlen < 0) return tlen; else pos += tlen;

    return pos;
}

int float64::_getEncodedSizeNoHash() const
{
    int enc_size = 0;
    enc_size += __double_encoded_array_size(NULL, 1);
    return enc_size;
}

uint64_t float64::_computeHash(const __lcm_hash_ptr *p)
{
    const __lcm_hash_ptr *fp;
    for(fp = p; fp != NULL; fp = fp->parent)
        if(fp->v == float64::getHash)
            return 0;
    const __lcm_hash_ptr cp = { p, (void*)float64::getHash };

    uint64_t hash = 0x1234567890abcdefLL;

    return (hash<<1) + ((hash>>63)&1);
}

}

#endif
