pragma solidity ^0.4.23;

import "./lib/RLP.sol";
import "./lib/ArrayUint.sol";

/**
 * @title CongestionValidator
 * 
 * CongestionValidator can be used by microraiden to prevent stale state attacks in 
 * congested networks.
 * 
 * @author Tim-Jonas Schwarz (tmjssz@gmail.com)
 */
contract CongestionValidator {

    using RLP for RLP.RLPItem;
    using RLP for bytes;
    using ArrayUint for uint[];

    struct BlockHeader {
        bytes32 blockHash;
        uint gasFree;
        uint gasLimit;
        uint gasUsed;
        uint number;
    }

    /// Store every valid reported block header mapped by its number. 
    mapping(uint => BlockHeader) reportedBlocks;

    /// @notice Function verifies the given list of block headers and returns the number of 
    /// uncongested blocks.
    /// @param rlpHeaders RLP encoded list of block headers that shall be checked.
    /// @param minGasFree The minimum amount of gas that must still be free in the block in
    /// order to become approved as uncongested.
    /// @param minBlockNumber The minimum block number to be approved as valid. Block headers
    /// from the rlpHeaders parameter that have a smaller number are not counted, even if 
    /// they have enough free space.
    function numBlocksUncongested(
        bytes memory rlpHeaders,
        uint minGasFree,
        uint minBlockNumber
    ) public view returns (uint) {
        if (minBlockNumber > block.number) {
            // Minimum block number is not yet existing.
            return 0;
        }

        // Parse RLP data.
        uint[] memory blockNumbers = validateRLPHeaders(rlpHeaders);

        // Remove duplicates.
        blockNumbers = blockNumbers.removeDuplicates();

        // Counter for uncongested block headers.
        uint uncongestedBlocks = 0;
        
        // Verify all given block headers.
        for (uint i = 0; i < blockNumbers.length; i++) {
            uint blockNumber = blockNumbers[i];

            // Skip block numbers that are too low.
            if (blockNumber < minBlockNumber) {
                continue;
            }

            // Check if block is congested.
            BlockHeader memory blockHeader = reportedBlocks[blockNumber];
            if (blockHeader.gasFree >= minGasFree) {
                uncongestedBlocks++;
            }
        }
        
        return uncongestedBlocks;
    }

    /// @notice Parses and validates a RLP encoded list of block headers
    /// @param rlpHeaders The RLP encoded list of block headers.
    /// @return List of numbers of valid blocks.
    function validateRLPHeaders(bytes memory rlpHeaders) private returns (uint[] memory) {
        // Decode RLP data.
        RLP.RLPItem[] memory rlpItems = rlpHeaders.toRLPItem().toList();

        uint[] memory blockNumbers = new uint[](0);

        // Parse block headers.
        for (uint i = 0; i < rlpItems.length; i++) {
            BlockHeader memory blockHeader = parseRLPHeader(rlpItems[i]);

            // Validate the block header.
            if (reportedBlocks[blockHeader.number].blockHash == 0x0) {
                // Block has not been reported yet -> validate it.
                if (blockHeaderIsValid(blockHeader)) {
                    // Store valid block in global mapping of reported block headers.
                    reportedBlocks[blockHeader.number] = blockHeader;
                } else {
                    // Skip invalid header.
                    continue;
                }
            } else {
                // Block with the given number has already been validated before.
                if (blockHeader.blockHash != reportedBlocks[blockHeader.number].blockHash) {
                    // Block hash is incorrect -> Skip invalid header.
                    continue;
                }
            }

            blockNumbers = blockNumbers.append(blockHeader.number);
        }
        
        return blockNumbers;
    }

    /// @notice Verfiy that the given block header is valid and belongs to one of the last 
    ///         256 generated blocks.
    /// @param blockHeader The block header.
    /// @return Wether the block header is valid or not.
    function blockHeaderIsValid(BlockHeader blockHeader) internal view returns (bool) {
        // Make sure that given block is one of the last 256 blocks.
        require(blockHeader.number < block.number, "Block number is not yet existing.");
        require(blockHeader.number + 256 > block.number, "Too old block.");
                
        // Validate given block header by its hash.
        return blockHeader.blockHash == blockhash(blockHeader.number);
    }
    
    /// @notice Parses a RLP item to a block header object
    /// @param rlpItem The RLP item of a block header.
    /// @return Parsed block header.
    function parseRLPHeader(RLP.RLPItem rlpItem) internal returns (BlockHeader memory) {
        BlockHeader memory header;

        // Transform the item to a list.
        RLP.RLPItem[] memory headerRlpItems = rlpItem.toList();

        // Calculate the blockhash from RLP encoded block header.
        header.blockHash = keccak256(rlpItem.toBytes());

        // Parse the block number.
        header.number = headerRlpItems[8].toUint();

        // Parse gas limit.
        if (headerRlpItems[9].isEmpty()) {
            header.gasLimit = 0;
        } else {
            header.gasLimit = headerRlpItems[9].toUint();
        }

        // Parse gas used.
        if (headerRlpItems[10].isEmpty()) {
            header.gasUsed = 0;
        } else {
            header.gasUsed = headerRlpItems[10].toUint();
        }

        // Calculate left free gas in block from its gasLimit and gasUsed.
        header.gasFree = header.gasLimit - header.gasUsed;

        return header;
    }
}
