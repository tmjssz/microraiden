pragma solidity ^0.4.23;

/**
* @title ArrayUint
*
* Util functions for working with arrays of uint values.
*
* @author Tim-Jonas Schwarz (tmjssz@gmail.com)
*/
library ArrayUint {

    using ArrayUint for uint[];

    /// @dev Removes duplicate values from the array.
    /// @param self The array.
    /// @return New array containing only unique values.
    function removeDuplicates(uint[] memory self) internal pure returns (uint[] memory) {
        uint[] memory arrayUnique = new uint[](0);

        for (uint i = 0; i < self.length; i++) {
            if (arrayUnique.contains(self[i]) < 0) {
                arrayUnique = arrayUnique.append(self[i]);
            }
        }

        delete self;
        return arrayUnique;
    }

    /// @dev Checks wether a given value is contained in the array.
    /// @param self The array.
    /// @param value The uint value that should be checked to exist in the array.
    /// @return Index of the value inside the array. If the value is not contained,
    ///         the return value is -1.
    function contains(uint[] self, uint value) internal pure returns(int) {
        for (uint i = 0; i < self.length; i++) {
            if (self[i] == value) {
                return int(i);
            }
        }

        // The value was not found in the array.
        return -1;
    }

    /// @dev Appends a given value to the end of the array.
    /// @param self The array.
    /// @param value The uint value that should be appended to the array.
    /// @return New array containing all values of the given array + the given value.
    function append(uint[] self, uint value) internal pure returns(uint[]) {
        uint[] memory arrayNew = new uint[](self.length+1);

        for (uint i = 0; i < self.length; i++) {
            arrayNew[i] = self[i];
        }
        
        arrayNew[self.length] = value;
        
        delete self;
        return arrayNew;
    }

    /// @dev Removes the value at the given index from the array.
    /// @param self The array.
    /// @param index The index of the element that should be returned.
    /// @return New array containing all values of the given array except the removed element.
    function remove(uint[] self, uint index) internal pure returns(uint[] value) {
        if (index >= self.length) return;

        uint[] memory arrayNew = new uint[](self.length-1);
        for (uint i = 0; i < arrayNew.length; i++){
            if (i != index && i < index){
                arrayNew[i] = self[i];
            } else {
                arrayNew[i] = self[i+1];
            }
        }

        delete self;
        return arrayNew;
    }

}